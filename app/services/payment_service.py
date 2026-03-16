"""Stripe payment and checkout logic."""
from app.core.config import get_settings

settings = get_settings()


class PaymentService:
    """Stripe checkout session and webhook handling."""

    REPORT_PRICE_CENTS = 9900  # $99.00
    REPORT_PRODUCT_TYPE = "report"

    @staticmethod
    def is_configured() -> bool:
        """Check if Stripe is configured."""
        return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID_REPORT)

    @staticmethod
    async def create_checkout_session(
        assessment_id: int,
        user_id: int,
        user_email: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """
        Create Stripe Checkout session for report purchase.
        Returns {checkout_url, session_id} or raises if not configured.
        """
        if not PaymentService.is_configured():
            raise ValueError("Stripe is not configured")
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": settings.STRIPE_PRICE_ID_REPORT,
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user_email,
            metadata={"assessment_id": str(assessment_id), "user_id": str(user_id)},
        )
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
