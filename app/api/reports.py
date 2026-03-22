"""Report endpoints - paid readiness reports."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import os

from app.core.database import get_db
from app.core.config import get_settings
from app.core.auth import get_current_user_required
from app.models.user import User
from app.models.report import Report
from app.models.assessment import Assessment
from app.schemas.report import CheckoutRequest, CheckoutResponse
from app.schemas.saq_assessment import GuestCheckoutRequest, GuestCheckoutResponse
from app.services.payment_service import PaymentService
from app.services.report_service import ReportService
from app.services.assessment_service import AssessmentService
from app.services.checkout_completion import fulfill_paid_checkout_session
from app.core.exceptions import ValidationError

router = APIRouter()
settings = get_settings()


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Create Stripe Checkout session for report purchase."""
    assessment = await AssessmentService.get_or_404(db, data.assessment_id)
    if assessment.user_id != current_user.id:
        raise ValidationError("Assessment must belong to you to purchase report")
    if assessment.status != "completed":
        raise ValidationError("Complete the assessment before purchasing report")
    success_url = f"{settings.FRONTEND_URL}/dashboard?report=success"
    cancel_url = f"{settings.FRONTEND_URL}/assessments/{assessment.id}/results"

    if PaymentService.is_configured():
        result = await PaymentService.create_checkout_session(
            assessment_id=assessment.id,
            user_id=current_user.id,
            user_email=current_user.email,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        report = await ReportService.create_for_assessment(
            db, current_user.id, assessment.id, stripe_payment_id=result["session_id"]
        )
        return CheckoutResponse(**result)

    # Dev bypass: when Stripe not configured, create report, generate PDF, and redirect to success
    if settings.STRIPE_DEV_BYPASS:
        report = await ReportService.create_for_assessment(
            db, current_user.id, assessment.id, stripe_payment_id="dev_bypass"
        )
        await db.flush()
        # Generate PDF immediately (same flow as Stripe webhook)
        report.status = "generating"
        await db.flush()
        file_path = ReportService.generate_pdf_sync(
            report_id=report.id,
            assessment_id=assessment.id,
            environment_type=assessment.environment_type or "ecommerce",
            scope_result=assessment.scope_result or {},
        )
        if file_path:
            report.file_path = file_path
            report.status = "generated"
        else:
            report.status = "failed"
        await db.flush()
        return CheckoutResponse(checkout_url=success_url, session_id="dev_bypass")

    raise HTTPException(
        503,
        "Payment system not configured. Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID_REPORT in .env, or STRIPE_DEV_BYPASS=true for development.",
    )


@router.post("/checkout-guest", response_model=GuestCheckoutResponse)
async def create_checkout_guest(
    data: GuestCheckoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Guest checkout for SAQ wizard — no login required.
    Sync assessment first via POST /api/assessments/saq-sync.
    """
    result = await db.execute(select(Assessment).where(Assessment.id == data.assessment_id))
    assessment = result.scalar_one_or_none()
    if not assessment or assessment.anonymous_id != data.client_session_id.strip()[:64]:
        raise HTTPException(400, "Invalid assessment or session — refresh and try again")
    if not assessment.scope_result:
        raise HTTPException(400, "Assessment has no results yet")
    email = str(data.email).strip().lower()
    assessment.guest_email = email

    await db.execute(
        delete(Report).where(Report.assessment_id == assessment.id, Report.user_id.is_(None))
    )
    await db.flush()

    success_url = (
        f"{settings.FRONTEND_URL}/dashboard?report=success&session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = f"{settings.FRONTEND_URL}/assessments/session/{data.client_session_id}"

    if settings.STRIPE_DEV_BYPASS and not PaymentService.is_configured():
        await ReportService.create_pending_guest(db, assessment.id, stripe_payment_id="dev_bypass")
        await db.flush()
        out = await fulfill_paid_checkout_session(
            db,
            "dev_bypass",
            dev_bypass=True,
            dev_email=email,
            dev_assessment_id=assessment.id,
        )
        if not out.get("ok") or not out.get("access_token"):
            raise HTTPException(500, "Dev checkout fulfillment failed")
        return GuestCheckoutResponse(
            checkout_url=f"{settings.FRONTEND_URL}/dashboard?report=success",
            session_id="dev_bypass",
            access_token=out["access_token"],
        )

    if not PaymentService.is_configured():
        raise HTTPException(
            503,
            "Payment not configured. Set Stripe keys or STRIPE_DEV_BYPASS=true for development.",
        )

    co = await PaymentService.create_guest_checkout_session(
        assessment_id=assessment.id,
        client_session_id=data.client_session_id,
        customer_email=email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await ReportService.create_pending_guest(db, assessment.id, stripe_payment_id=co["session_id"])
    await db.flush()
    return GuestCheckoutResponse(checkout_url=co["checkout_url"], session_id=co["session_id"])


@router.get("/{report_id}/download")
async def download_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report or report.user_id != current_user.id:
        raise HTTPException(404, "Report not found")
    if report.status != "generated":
        raise HTTPException(404, "Report not yet generated")
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(404, "Report file not found")
    return FileResponse(report.file_path, filename="compliance-readiness-report.pdf")
