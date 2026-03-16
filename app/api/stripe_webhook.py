"""Stripe webhook handler for payment completion.

Phase 8: Idempotent handling, failure recovery.
- Report not found: return 200 (no action, Stripe stops retrying)
- Report already generated: skip PDF, return 200
- Report generating/failed: re-run PDF (retry on webhook replay)
"""
import logging
import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.report import Report
from app.models.assessment import Assessment

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe checkout.session.completed and other payment events."""
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
        metadata = session.get("metadata", {})
        assessment_id = int(metadata.get("assessment_id", 0))
        user_id = int(metadata.get("user_id", 0))
        if not assessment_id or not user_id:
            logger.warning("Webhook: missing assessment_id or user_id in metadata")
            return {"received": True}

        result = await db.execute(
            select(Report).where(Report.stripe_payment_id == session_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            logger.info("Webhook: Report not found for session %s (idempotent)", session_id[:20])
            return {"received": True}

        # Idempotent: already generated, skip
        if report.status == "generated":
            return {"received": True}

        report.status = "generating"
        await db.flush()

        assessment_result = await db.execute(
            select(Assessment).where(Assessment.id == assessment_id)
        )
        assessment = assessment_result.scalar_one_or_none()
        if not assessment or not assessment.scope_result:
            report.status = "failed"
            await db.flush()
            logger.warning("Webhook: Assessment %s not found or has no scope_result", assessment_id)
            return {"received": True}

        from app.services.report_service import ReportService
        file_path = ReportService.generate_pdf_sync(
            report_id=report.id,
            assessment_id=assessment_id,
            environment_type=assessment.environment_type or "ecommerce",
            scope_result=assessment.scope_result,
        )
        if file_path:
            report.file_path = file_path
            report.status = "generated"
        else:
            report.status = "failed"
            logger.error("Webhook: PDF generation failed for report %s", report.id)
        await db.flush()

    return {"received": True}
