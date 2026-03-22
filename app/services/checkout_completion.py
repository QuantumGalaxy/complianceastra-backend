"""Fulfill paid Stripe checkout: create/link user, report, PDF (idempotent)."""
from __future__ import annotations

import logging
import secrets
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_password_hash, create_access_token
from app.core.config import get_settings
from app.models.assessment import Assessment
from app.models.report import Report
from app.models.user import User
from app.services.report_service import ReportService

settings = get_settings()
logger = logging.getLogger(__name__)


def _get_session_email(session: dict[str, Any]) -> str | None:
    email = session.get("customer_email") or session.get("customer_details", {}).get("email")
    if email:
        return str(email).strip().lower()
    meta = session.get("metadata") or {}
    ce = meta.get("customer_email")
    return str(ce).strip().lower() if ce else None


async def get_or_create_user_for_guest(
    db: AsyncSession,
    email: str,
) -> tuple[User, str | None]:
    """
    Return (user, plain_password_or_none).
    If user is new, creates account with random password (returned once for email body).
    """
    email_norm = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email_norm))
    existing = result.scalar_one_or_none()
    if existing:
        return existing, None
    plain = secrets.token_urlsafe(14)
    user = User(
        email=email_norm,
        hashed_password=get_password_hash(plain),
        full_name=None,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user, plain


async def fulfill_paid_checkout_session(
    db: AsyncSession,
    stripe_session_id: str,
    *,
    session_data: dict[str, Any] | None = None,
    dev_bypass: bool = False,
    dev_email: str | None = None,
    dev_assessment_id: int | None = None,
) -> dict[str, Any]:
    """
    Idempotent: assign user + assessment + generate PDF for a paid session.
    Returns { ok, user_id, report_id, access_token?, new_password_plain? }.
    """
    if dev_bypass and settings.STRIPE_DEV_BYPASS:
        if not dev_email or not dev_assessment_id:
            return {"ok": False, "error": "dev_missing_params"}
        result = await db.execute(select(Assessment).where(Assessment.id == dev_assessment_id))
        assessment = result.scalar_one_or_none()
        if not assessment or not assessment.scope_result:
            return {"ok": False, "error": "assessment_not_found"}
        user, plain = await get_or_create_user_for_guest(db, dev_email)
        assessment.user_id = user.id
        if assessment.guest_email:
            assessment.guest_email = None
        r = await db.execute(
            select(Report).where(Report.stripe_payment_id == "dev_bypass", Report.assessment_id == assessment.id)
        )
        report = r.scalar_one_or_none()
        if not report:
            r2 = await db.execute(
                select(Report).where(
                    Report.assessment_id == assessment.id,
                    Report.user_id.is_(None),
                )
            )
            report = r2.scalars().first()
        if not report:
            report = Report(
                user_id=None,
                assessment_id=assessment.id,
                stripe_payment_id="dev_bypass",
                status="pending",
            )
            db.add(report)
            await db.flush()
        report.user_id = user.id
        report.status = "generating"
        await db.flush()
        file_path = ReportService.generate_pdf_sync(
            report_id=report.id,
            assessment_id=assessment.id,
            environment_type=assessment.environment_type or "ecommerce",
            scope_result=assessment.scope_result,
        )
        if file_path:
            report.file_path = file_path
            report.status = "generated"
        else:
            report.status = "failed"
        await db.flush()
        token = create_access_token({"sub": str(user.id)})
        return {
            "ok": True,
            "user_id": user.id,
            "report_id": report.id,
            "access_token": token,
            "new_password_plain": plain,
        }

    if session_data is not None:
        session = session_data
    else:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(stripe_session_id)
        except Exception as e:
            logger.exception("Stripe retrieve failed: %s", e)
            return {"ok": False, "error": "stripe_retrieve_failed"}

    if session.get("payment_status") != "paid":
        return {"ok": False, "error": "not_paid"}

    session_id = session.get("id") or stripe_session_id
    meta = session.get("metadata") or {}
    try:
        assessment_id = int(meta.get("assessment_id", 0))
    except (TypeError, ValueError):
        assessment_id = 0
    if not assessment_id:
        return {"ok": False, "error": "missing_assessment_id"}

    email = _get_session_email(session)
    if not email:
        return {"ok": False, "error": "missing_email"}

    result = await db.execute(select(Report).where(Report.stripe_payment_id == session_id))
    report = result.scalar_one_or_none()
    if not report:
        a_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
        assessment_recover = a_result.scalar_one_or_none()
        if assessment_recover and assessment_recover.scope_result:
            report = Report(
                user_id=None,
                assessment_id=assessment_id,
                stripe_payment_id=session_id,
                status="pending",
            )
            db.add(report)
            await db.flush()
            await db.refresh(report)
            logger.info("Recovered missing report row for session %s", session_id[:16] if session_id else "")
        else:
            logger.warning("No report row for session %s", session_id[:20] if session_id else "")
            return {"ok": False, "error": "report_not_found"}

    if report.assessment_id != assessment_id:
        return {"ok": False, "error": "assessment_mismatch"}

    a_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = a_result.scalar_one_or_none()
    if not assessment or not assessment.scope_result:
        report.status = "failed"
        await db.flush()
        return {"ok": False, "error": "assessment_invalid"}

    user, plain = await get_or_create_user_for_guest(db, email)
    report.user_id = user.id
    assessment.user_id = user.id
    assessment.guest_email = None
    assessment.status = "completed"

    if report.status == "generated" and report.file_path:
        token = create_access_token({"sub": str(user.id)})
        return {
            "ok": True,
            "user_id": user.id,
            "report_id": report.id,
            "access_token": token,
            "new_password_plain": plain,
        }

    report.status = "generating"
    await db.flush()

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
        logger.error("PDF generation failed for report %s", report.id)
    await db.flush()

    token = create_access_token({"sub": str(user.id)})
    return {
        "ok": True,
        "user_id": user.id,
        "report_id": report.id,
        "access_token": token,
        "new_password_plain": plain,
    }
