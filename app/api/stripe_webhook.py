"""Stripe webhook handler for payment completion."""
import logging
import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.services.checkout_completion import fulfill_paid_checkout_session

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe checkout.session.completed — idempotent fulfillment."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        if not session_id:
            return {"received": True}
        out = await fulfill_paid_checkout_session(db, session_id, session_data=session)
        if not out.get("ok"):
            logger.warning("Webhook fulfillment: %s for session %s", out.get("error"), session_id[:16])
    return {"received": True}
