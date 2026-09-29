from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select

from .config import settings
from .db import SessionLocal
from .knowledge import embedding, split_source_text, tokens
from .models import (
    ActionLedger,
    Approval,
    Chunk,
    Conversation,
    Customer,
    Document,
    DocumentVersion,
    Event,
    GuestChallenge,
    IngestionJob,
    Message,
    Order,
    OrderLine,
    Product,
    ReturnRecord,
    ReturnRequest,
    SessionToken,
    Shipment,
    Ticket,
    User,
    Workspace,
)
from .security import hash_password

ROOT = Path(__file__).resolve().parents[4]
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=850, chunk_overlap=125)


def dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def migrate() -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")


def reset_demo(db, workspace_ids: list[str]) -> None:
    if settings.connected:
        raise RuntimeError("Demo reset is unavailable in CONNECTED mode")
    conversation_ids = db.scalars(select(Conversation.id).where(Conversation.workspace_id.in_(workspace_ids))).all()
    document_ids = db.scalars(select(Document.id).where(Document.workspace_id.in_(workspace_ids))).all()
    version_ids = db.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id.in_(document_ids))).all() if document_ids else []
    order_ids = db.scalars(select(Order.id).where(Order.workspace_id.in_(workspace_ids))).all()
    user_ids = db.scalars(select(User.id).where(User.workspace_id.in_(workspace_ids))).all()
    proposal_ids = db.scalars(select(ReturnRequest.id).where(ReturnRequest.workspace_id.in_(workspace_ids))).all()
    db.execute(delete(Approval).where(Approval.workspace_id.in_(workspace_ids)))
    db.execute(delete(ReturnRecord).where(ReturnRecord.workspace_id.in_(workspace_ids)))
    db.execute(delete(ActionLedger).where(ActionLedger.workspace_id.in_(workspace_ids)))
    db.execute(delete(ReturnRequest).where(ReturnRequest.id.in_(proposal_ids)))
    db.execute(delete(Ticket).where(Ticket.workspace_id.in_(workspace_ids)))
    db.execute(delete(Event).where(Event.workspace_id.in_(workspace_ids)))
    if conversation_ids:
        db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    db.execute(delete(Conversation).where(Conversation.workspace_id.in_(workspace_ids)))
    if order_ids:
        db.execute(delete(GuestChallenge).where(GuestChallenge.order_id.in_(order_ids)))
        db.execute(delete(Shipment).where(Shipment.order_id.in_(order_ids)))
        db.execute(delete(OrderLine).where(OrderLine.order_id.in_(order_ids)))
    db.execute(delete(Order).where(Order.workspace_id.in_(workspace_ids)))
    db.execute(delete(Chunk).where(Chunk.workspace_id.in_(workspace_ids)))
    db.execute(delete(IngestionJob).where(IngestionJob.workspace_id.in_(workspace_ids)))
    if version_ids:
        db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    db.execute(delete(Document).where(Document.workspace_id.in_(workspace_ids)))
    db.execute(delete(Product).where(Product.workspace_id.in_(workspace_ids)))
    if user_ids:
        db.execute(delete(SessionToken).where(SessionToken.user_id.in_(user_ids)))
    db.execute(delete(User).where(User.workspace_id.in_(workspace_ids)))
    db.execute(delete(Customer).where(Customer.workspace_id.in_(workspace_ids)))
    db.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
    db.commit()
    # A reset replaces these synthetic workspaces. Their paused graph state and
    # uploaded source files belong to the same namespace as the deleted rows.
    if settings.database_url.startswith("sqlite:///"):
        checkpoint_path = Path(settings.database_url.removeprefix("sqlite:///") + ".checkpoints")
        if checkpoint_path.exists():
            with sqlite3.connect(checkpoint_path) as checkpoints:
                tables = {row[0] for row in checkpoints.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")}
                for table in ("writes", "checkpoints"):
                    if table not in tables:
                        continue
                    for workspace_id in workspace_ids:
                        for prefix in (f"chat:{workspace_id}:", f"return:{workspace_id}:"):
                            checkpoints.execute(
                                f"DELETE FROM {table} WHERE substr(thread_id, 1, ?) = ?",
                                (len(prefix), prefix),
                            )
    upload_root = settings.upload_root.resolve()
    for workspace_id in workspace_ids:
        target = (upload_root / workspace_id).resolve()
        if target.parent != upload_root:
            raise RuntimeError("Demo upload reset escaped the configured upload directory")
        if target.is_dir():
            shutil.rmtree(target)


def seed(path: Path, *, reset: bool = False) -> dict:
    if settings.connected:
        raise RuntimeError("Synthetic seed requires APP_MODE=DEMO")
    data = json.loads(path.read_text(encoding="utf-8"))
    workspace_ids = [row["id"] for row in data["workspaces"]]
    with SessionLocal() as db:
        existing = db.scalar(select(Workspace.id).where(Workspace.id.in_(workspace_ids)).limit(1))
        if existing and not reset:
            raise RuntimeError("Demo workspace already exists; use --reset to replace only seeded workspaces")
        if existing:
            reset_demo(db, workspace_ids)
        db.add_all([Workspace(id=row["id"], name=row["name"],
                              policy_priority=["official_policy", "product_manual", "faq"],
                              return_policy=row.get("return_policy", {}))
                    for row in data["workspaces"]])
        db.flush()
        db.add_all([Customer(id=row["id"], workspace_id=row["workspace_id"],
                             name=row["name"], email=row["email"])
                    for row in data["customers"]])
        db.flush()
        db.add_all([User(id=row["id"], workspace_id=row["workspace_id"],
                         customer_id=row.get("customer_id"), email=row["email"].lower(),
                         name=row["name"], role=row["role"],
                         password_hash=hash_password(row["password"]), active=True)
                    for row in data["users"]])
        db.add_all([Product(id=row["id"], workspace_id=row["workspace_id"],
                            sku=row["sku"], name=row["name"], category=row["category"],
                            price_cents=row["price_cents"], specifications=row.get("specifications", {}))
                    for row in data["products"]])
        db.flush()
        for row in data["orders"]:
            db.add(Order(id=row["id"], workspace_id=row["workspace_id"],
                         customer_id=row["customer_id"], number=row["number"],
                         placed_at=dt(row["placed_at"]), status=row["status"],
                         total_cents=row["total_cents"]))
            for line in row["lines"]:
                db.add(OrderLine(id=line["id"], order_id=row["id"], product_id=line["product_id"],
                                 quantity=line["quantity"], unit_price_cents=line["unit_price_cents"],
                                 returned_quantity=line.get("returned_quantity", 0)))
            for shipment in row.get("shipments", []):
                db.add(Shipment(id=shipment["id"], order_id=row["id"], status=shipment["status"],
                                carrier=shipment.get("carrier"), tracking_code=shipment.get("tracking_code"),
                                shipped_at=dt(shipment.get("shipped_at")),
                                delivered_at=dt(shipment.get("delivered_at")),
                                promised_delivery_at=dt(shipment.get("promised_delivery_at"))))
        db.commit()

        first_chunk_by_version: dict[str, dict] = {}
        for row in data["documents"]:
            db.add(Document(id=row["id"], workspace_id=row["workspace_id"],
                            title=row["title"], kind=row["kind"], category=row["category"],
                            authority=row.get("authority", "uploaded"),
                            status=row["status"], current_version=row["current_version"],
                            updated_at=dt(row["versions"][-1].get("published_at"))))
            for version in row["versions"]:
                raw = version["content"].encode("utf-8")
                digest = hashlib.sha256(raw).hexdigest()
                if digest != version["sha256"]:
                    raise RuntimeError(f"Fixture hash mismatch: {version['id']}")
                directory = settings.upload_root / row["workspace_id"] / row["id"]
                directory.mkdir(parents=True, exist_ok=True)
                storage_path = directory / f"seed-v{version['version']}.md"
                storage_path.write_bytes(raw)
                db.add(DocumentVersion(id=version["id"], document_id=row["id"],
                    version=version["version"], sha256=digest, storage_path=str(storage_path),
                    effective_from=dt(version.get("effective_from")),
                    effective_to=dt(version.get("effective_to")),
                    published_at=dt(version.get("published_at"))))
                for ordinal, content in enumerate(split_source_text(version["content"])):
                    chunk_id = f"{version['id']}_c{ordinal + 1}"
                    section = next((line.lstrip("# ") for line in version["content"].splitlines()
                                    if line.startswith("#")), "Overview")[:200]
                    db.add(Chunk(id=chunk_id, workspace_id=row["workspace_id"],
                                 document_version_id=version["id"], section=section,
                                 page=1 if row["kind"] == "pdf" else None, ordinal=ordinal,
                                 content=content, search_text=" ".join(tokens(content)),
                                 embedding=embedding(content)))
                    if ordinal == 0:
                        first_chunk_by_version[version["id"]] = {
                            "chunk_id": chunk_id, "document_title": row["title"],
                            "version": version["version"], "section": section,
                            "page": 1 if row["kind"] == "pdf" else None,
                            "passage": content}
                if version["version"] == row["current_version"]:
                    db.add(IngestionJob(id=f"job_{row['id']}", workspace_id=row["workspace_id"],
                                        document_version_id=version["id"], status="completed",
                                        progress=100, error=None, attempts=1))
        db.commit()

        for row in data["conversations"]:
            db.add(Conversation(id=row["id"], workspace_id=row["workspace_id"],
                                customer_id=row["customer_id"], subject=row["subject"],
                                status=row["status"], updated_at=dt(row["updated_at"])))
            for message in row["messages"]:
                citations = [first_chunk_by_version[value] for value in message.get("citations", [])
                             if value in first_chunk_by_version]
                db.add(Message(id=message["id"], conversation_id=row["id"],
                               role=message["role"], content=message["content"],
                               citations=citations, next_action="none", missing_information=[],
                               created_at=dt(message["created_at"])))
        db.commit()

        for row in data["proposals"]:
            raw_policy = row.get("policy_result", {})
            policy = raw_policy if isinstance(raw_policy, dict) else {
                "eligible": row["status"] not in {"denied", "rejected"},
                "requires_review": row["requires_review"], "code": raw_policy,
                "explanation": "Synthetic historical proposal"}
            db.add(ReturnRequest(id=row["id"], workspace_id=row["workspace_id"],
                customer_id=row["customer_id"], conversation_id=row.get("conversation_id"),
                order_id=row["order_id"], line_id=row["line_id"], quantity=row["quantity"],
                condition=row["condition"], reason=row["reason"], policy_result=policy,
                status=row["status"], requires_review=row["requires_review"],
                version=str(row["version"]), expires_at=dt(row["expires_at"]),
                created_at=dt(row["created_at"])))
        db.commit()
    return {key: len(data[key]) for key in ("workspaces", "products", "customers", "orders", "documents", "conversations", "proposals")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the isolated synthetic SupportPilot demo")
    parser.add_argument("--size", choices=["small", "full"], default="small")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    migrate()
    path = ROOT / "fixtures" / f"demo_{args.size}.json"
    if not path.exists():
        raise SystemExit(f"Generate fixture first: {path}")
    print(seed(path, reset=args.reset))


if __name__ == "__main__":
    main()
