"""Forgot-password: create and consume one-time reset tokens (hashed in DB)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

TOKEN_BYTES = 32
TTL_HOURS = 24


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_password_reset_token(db: AsyncSession, user: User) -> str:
    """Invalidate prior unused tokens, store new hash, return raw token for email."""
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    expires = datetime.utcnow() + timedelta(hours=TTL_HOURS)
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw),
        expires_at=expires,
    )
    db.add(row)
    await db.flush()
    return raw


async def consume_password_reset_token(db: AsyncSession, raw: str) -> User | None:
    """Return user if token valid and unused; mark used."""
    if not raw or len(raw) < 10:
        return None
    th = hash_reset_token(raw.strip())
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == th))
    row = result.scalar_one_or_none()
    if not row or row.used_at is not None:
        return None
    if row.expires_at < datetime.utcnow():
        return None
    u_result = await db.execute(select(User).where(User.id == row.user_id))
    user = u_result.scalar_one_or_none()
    if not user:
        return None
    row.used_at = datetime.utcnow()
    await db.flush()
    return user
