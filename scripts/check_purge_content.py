"""Disposable SQLite smoke check for purge_content.py; never opens the demo DB."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sp-retention-", ignore_cleanup_errors=True) as folder:
        root = Path(folder)
        uploads = root / "uploads"
        os.environ["DATABASE_URL"] = f"sqlite:///{(root / 'probe.db').as_posix()}"
        os.environ["UPLOAD_ROOT"] = str(uploads)

        from supportpilot.db import Base, SessionLocal, engine
        from supportpilot.models import (
            Conversation,
            Customer,
            Document,
            DocumentVersion,
            Event,
            Message,
            SessionToken,
            Ticket,
            User,
            Workspace,
        )

        Base.metadata.create_all(engine)
        old = datetime(2024, 1, 1, tzinfo=UTC)
        try:
            with SessionLocal.begin() as db:
                for suffix in ("one", "two"):
                    workspace = Workspace(id=f"ws_{suffix}", name=f"Workspace {suffix}",
                                          policy_priority=[], return_policy={})
                    customer = Customer(id=f"cust_{suffix}", workspace_id=workspace.id,
                                        name="Customer", email=f"{suffix}@example.test")
                    user = User(id=f"user_{suffix}", workspace_id=workspace.id,
                                customer_id=customer.id, email=customer.email,
                                name="Customer", role="customer", password_hash="fixture", active=True)
                    conversation = Conversation(id=f"conv_{suffix}", workspace_id=workspace.id,
                                                customer_id=customer.id, subject="Old",
                                                status="resolved", updated_at=old)
                    document = Document(id=f"doc_{suffix}", workspace_id=workspace.id,
                                        title="Deleted", kind="markdown", category="general",
                                        authority="uploaded", status="deleted", current_version=1,
                                        deleted_at=old, updated_at=old)
                    upload = uploads / workspace.id / document.id / "v1.md"
                    upload.parent.mkdir(parents=True, exist_ok=True)
                    upload.write_text("old raw source", encoding="utf-8")
                    db.add(workspace)
                    db.flush()
                    db.add(customer)
                    db.flush()
                    db.add_all([user, conversation, document])
                    db.flush()
                    db.add_all([
                        SessionToken(id=f"session_{suffix}", user_id=user.id,
                                     token_hash=suffix, expires_at=old, created_at=old),
                        Message(id=f"msg_{suffix}", conversation_id=conversation.id,
                                role="customer", content="old personal text", citations=[],
                                next_action="none", missing_information=[], created_at=old),
                        Event(id=f"event_{suffix}", workspace_id=workspace.id,
                              conversation_id=conversation.id, kind="tool_result",
                              detail={"old": True}, created_at=old),
                        DocumentVersion(id=f"ver_{suffix}", document_id=document.id,
                                        version=1, sha256="0" * 64,
                                        storage_path=str(upload), created_at=old),
                    ])
                protected = Conversation(id="conv_audit", workspace_id="ws_one",
                                         customer_id="cust_one", subject="Ticket audit",
                                         status="resolved", updated_at=old)
                db.add(protected)
                db.flush()
                db.add_all([
                    Ticket(id="ticket_audit", workspace_id="ws_one",
                           conversation_id=protected.id, subject="Keep context",
                           summary="Operator audit", status="resolved", updated_at=old),
                    Message(id="msg_audit", conversation_id=protected.id, role="customer",
                            content="ticket context", citations=[], next_action="none",
                            missing_information=[], created_at=old),
                    Event(id="event_audit", workspace_id="ws_one",
                          conversation_id=protected.id, kind="ticket_created",
                          detail={"ticket_id": "ticket_audit"}, created_at=old),
                ])

            command = [sys.executable, str(Path(__file__).with_name("purge_content.py")),
                       "--workspace-id", "ws_one", "--before", "2025-01-01"]
            dry = subprocess.run(command, check=True, capture_output=True, text=True)
            preview = json.loads(dry.stdout)
            assert preview["mode"] == "dry_run"
            assert (preview["messages"], preview["events"],
                    preview["expired_sessions"], preview["soft_deleted_upload_files"]) == (1, 1, 1, 1)
            assert not preview["unsafe_upload_paths"]
            with SessionLocal() as db:
                assert db.get(Message, "msg_one") and db.get(Message, "msg_two")
            assert (uploads / "ws_one" / "doc_one" / "v1.md").exists()

            applied = subprocess.run(command + ["--apply"], check=True,
                                     capture_output=True, text=True)
            assert json.loads(applied.stdout)["upload_files_removed"] == 1
            with SessionLocal() as db:
                assert db.get(Message, "msg_one") is None and db.get(Message, "msg_two")
                assert db.get(Message, "msg_audit")
                assert db.get(Event, "event_one") is None and db.get(Event, "event_two")
                assert db.get(Event, "event_audit")
                assert db.get(SessionToken, "session_one") is None and db.get(SessionToken, "session_two")
            assert not (uploads / "ws_one" / "doc_one" / "v1.md").exists()
            assert (uploads / "ws_two" / "doc_two" / "v1.md").exists()
            print("Disposable retention dry-run/apply scope check passed")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
