"""Report endpoints - paid readiness reports."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os

from app.core.database import get_db
from app.core.config import get_settings
from app.core.auth import get_current_user_required
from app.models.user import User
from app.models.report import Report
from app.models.assessment import Assessment
from app.schemas.report import CheckoutRequest, CheckoutResponse
from app.services.payment_service import PaymentService
from app.services.report_service import ReportService
from app.services.assessment_service import AssessmentService
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
