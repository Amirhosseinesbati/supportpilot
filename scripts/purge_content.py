"""Preview or purge a narrow, workspace-scoped set of expired support data.

Run from apps/api with ``uv run python ../../scripts/purge_content.py`` so the
installed supportpilot package and API configuration are used. Dry-run is the
default; --apply is required for any deletion.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from supportpilot.config import settings
from supportpilot.db import SessionLocal
from supportpilot.models import (
    Conversation,
    Document,
    DocumentVersion,
    Event,
    Message,
    ReturnRequest,
    SessionToken,
    Ticket,
    User,
    Workspace,
)


@dataclass(frozen=True)
class FileCandidate:
    version_id: str
    path: Path
    relative_path: str
    exists: bool


def cutoff_from_iso(raw: str) -> datetime:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--before must be YYYY-MM-DD") from error
    cutoff = datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
    if cutoff > datetime.now(UTC):
        raise argparse.ArgumentTypeError("--before cannot be in the future")
    return cutoff


def safe_file_candidate(
    version: DocumentVersion, *, root: Path, workspace_id: str, document_id: str
) -> FileCandidate:
    # Database values are treated as untrusted path components. Never follow a
    # symlink or accept a stored path outside this document's upload directory.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", workspace_id) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", document_id
    ):
        raise ValueError("Workspace/document ID is unsafe as a path component")
    stored = Path(version.storage_path)
    if not version.storage_path or not stored.name:
        raise ValueError("Stored upload path is empty")
    absolute = stored.absolute()
    expected = root / workspace_id / document_id
    try:
        relative = absolute.relative_to(expected)
    except ValueError as error:
        raise ValueError("Stored upload path is outside its workspace/document directory") from error
    if len(relative.parts) != 1 or relative.name in {".", ".."}:
        raise ValueError("Stored upload path is not a direct document file")
    for item in (root, root / workspace_id, expected, absolute):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Stored upload path contains a symlink or junction")
    if not absolute.resolve(strict=False).is_relative_to(expected.resolve(strict=False)):
        raise ValueError("Resolved upload path escapes its workspace/document directory")
    if absolute.exists() and not absolute.is_file():
        raise ValueError("Stored upload path is not a regular file")
    return FileCandidate(version.id, absolute, str(absolute.relative_to(root)), absolute.exists())


def collect(
    db: Session, *, workspace_id: str, cutoff: datetime, upload_root: Path
) -> tuple[dict[str, list[str]], list[FileCandidate], list[str]]:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("Workspace ID does not exist")

    # Keep ticket and return audit threads intact, including all of their
    # messages/events. Only old, resolved, unlinked conversation shells qualify.
    archived_conversations = db.scalars(
        select(Conversation.id)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.status == "resolved",
            Conversation.updated_at < cutoff,
            ~select(Ticket.id)
            .where(Ticket.conversation_id == Conversation.id)
            .exists(),
            ~select(ReturnRequest.id)
            .where(ReturnRequest.conversation_id == Conversation.id)
            .exists(),
        )
        .order_by(Conversation.id)
    ).all()
    messages: list[str] = []
    events: list[str] = []
    if archived_conversations:
        messages = list(
            db.scalars(
                select(Message.id)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.workspace_id == workspace_id,
                    Message.conversation_id.in_(archived_conversations),
                    Message.created_at < cutoff,
                )
                .order_by(Message.id)
            )
        )
        events = list(
            db.scalars(
                select(Event.id)
                .where(
                    Event.workspace_id == workspace_id,
                    Event.conversation_id.in_(archived_conversations),
                    Event.created_at < cutoff,
                )
                .order_by(Event.id)
            )
        )
    sessions = list(
        db.scalars(
            select(SessionToken.id)
            .join(User, SessionToken.user_id == User.id)
            .where(User.workspace_id == workspace_id, SessionToken.expires_at < cutoff)
            .order_by(SessionToken.id)
        )
    )

    files: list[FileCandidate] = []
    unsafe: list[str] = []
    versions = db.execute(
        select(DocumentVersion, Document.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.workspace_id == workspace_id, Document.deleted_at < cutoff)
        .order_by(Document.id, DocumentVersion.version)
    ).all()
    for version, document_id in versions:
        try:
            files.append(
                safe_file_candidate(
                    version, root=upload_root, workspace_id=workspace_id, document_id=document_id
                )
            )
        except ValueError as error:
            unsafe.append(f"{version.id}: {error}")
    return {
        "resolved_conversations": list(archived_conversations),
        "messages": messages,
        "events": events,
        "expired_sessions": sessions,
    }, files, unsafe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True, help="Exact existing workspace ID")
    parser.add_argument(
        "--before", required=True, type=cutoff_from_iso,
        help="UTC cutoff YYYY-MM-DD; only older records qualify",
    )
    parser.add_argument("--apply", action="store_true", help="Perform the reviewed deletions")
    args = parser.parse_args()
    # Keep the configured spelling for the lexical scope check. On Windows a
    # resolved path may expand an 8.3 user profile name, while stored paths
    # retain the short spelling. The second check above compares real paths.
    upload_root = settings.upload_root.absolute()
    try:
        with SessionLocal() as db:
            ids, files, unsafe = collect(
                db, workspace_id=args.workspace_id, cutoff=args.before, upload_root=upload_root
            )
            result = {
                "mode": "apply" if args.apply else "dry_run",
                "workspace_id": args.workspace_id,
                "before_utc": args.before.isoformat(),
                "resolved_conversation_shells": len(ids["resolved_conversations"]),
                "messages": len(ids["messages"]),
                "events": len(ids["events"]),
                "expired_sessions": len(ids["expired_sessions"]),
                "soft_deleted_upload_files": sum(item.exists for item in files),
                "already_missing_upload_files": sum(not item.exists for item in files),
                "upload_files_sample": [item.relative_path for item in files[:20]],
                "unsafe_upload_paths": unsafe,
            }
            if args.apply:
                if unsafe:
                    raise ValueError("Unsafe upload paths found; no deletion performed")
                for model, key in (
                    (Message, "messages"),
                    (Event, "events"),
                    (SessionToken, "expired_sessions"),
                ):
                    if ids[key]:
                        db.execute(delete(model).where(model.id.in_(ids[key])))
                db.commit()
                removed = 0
                for item in files:
                    if item.exists:
                        item.path.unlink()
                        removed += 1
                result["upload_files_removed"] = removed
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"purge_content: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
