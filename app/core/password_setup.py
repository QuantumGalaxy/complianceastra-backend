"""JWT tokens for first-time password setup after Stripe checkout (deterministic per session)."""
from __future__ import annotations

from datetime import datetime, timedelta

from jose import jwt

from app.core.config import get_settings

PWD_SETUP_TYP = "pwd_setup"


def create_password_setup_token(user_id: int, stripe_session_id: str) -> str:
    """Signed JWT bound to checkout session; same inputs yield the same token (idempotent post-checkout)."""
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {
        "sub": str(user_id),
        "typ": PWD_SETUP_TYP,
        "sid": stripe_session_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
