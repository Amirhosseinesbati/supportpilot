from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import SessionToken, User, now

COOKIE_NAME = "supportpilot_session"
password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_session(db: Session, user: User, response: Response) -> None:
    raw = secrets.token_urlsafe(32)
    db.add(SessionToken(user_id=user.id, token_hash=token_digest(raw),
                        expires_at=now() + timedelta(hours=settings.session_hours)))
    db.commit()
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=settings.cookie_secure,
                        samesite="strict", max_age=settings.session_hours * 3600, path="/")


def current_user(db: Session = Depends(get_db),
                 raw: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> User:
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in is required")
    session = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_digest(raw)))
    if session is None or session.expires_at.replace(tzinfo=None) <= now().replace(tzinfo=None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return dependency


def revoke_session(db: Session, raw: str | None, response: Response) -> None:
    if raw:
        session = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_digest(raw)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
