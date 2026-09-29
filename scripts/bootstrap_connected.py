"""Create the first customer workspace/admin without shipping a default password."""

from __future__ import annotations

import argparse
from getpass import getpass

from sqlalchemy import select

from supportpilot.config import settings
from supportpilot.db import SessionLocal
from supportpilot.models import User, Workspace
from supportpilot.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Customer installation name")
    parser.add_argument("--email", required=True, help="Initial administrator email")
    parser.add_argument("--name", default="Administrator", help="Administrator display name")
    args = parser.parse_args()

    if not settings.connected:
        raise SystemExit("Bootstrap is only available with APP_MODE=CONNECTED")
    if not settings.database_url.startswith("postgresql"):
        raise SystemExit("Bootstrap requires a PostgreSQL DATABASE_URL")
    workspace_name = args.workspace.strip()
    email = args.email.strip().lower()
    if not workspace_name or len(workspace_name) > 120:
        raise SystemExit("Workspace name must contain 1 to 120 characters")
    if not email or "@" not in email or len(email) > 255:
        raise SystemExit("Provide a valid administrator email")
    password = getpass("Initial administrator password (16+ characters): ")
    if len(password) < 16 or password != getpass("Repeat password: "):
        raise SystemExit("Passwords differ or are shorter than 16 characters")

    with SessionLocal.begin() as db:
        if db.scalar(select(Workspace.id).limit(1)):
            raise SystemExit("This installation already has a workspace; no changes made")
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("Administrator email already exists; no changes made")
        workspace = Workspace(name=workspace_name,
                              policy_priority=["official_policy", "product_manual", "faq"],
                              return_policy={})
        db.add(workspace)
        db.flush()
        db.add(User(workspace_id=workspace.id, customer_id=None, email=email,
                    name=args.name.strip() or "Administrator", role="admin",
                    password_hash=hash_password(password), active=True))
        workspace_id = workspace.id
    print(f"Created workspace {workspace_id} and administrator {email}")


if __name__ == "__main__":
    main()
