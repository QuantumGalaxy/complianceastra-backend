"""Phase 7: Professional paid report generation and storage."""
import os
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import NotFoundError

settings = get_settings()

# Environment type display names
ENV_DISPLAY = {
    "ecommerce": "Ecommerce",
    "pos": "POS",
    "payment_platform": "Payment Platform",
}

# Classification display names (snake_case -> Title Case)
CLASSIFICATION_DISPLAY = {
    "redirect_only_checkout": "Redirect-Only Checkout",
    "hosted_fields_checkout": "Hosted Fields Checkout",
    "direct_api_checkout": "Direct API Checkout",
    "card_data_storage": "Card Data Storage",
    "p2pe_standalone": "P2PE Standalone Terminals",
    "integrated_pos": "Integrated POS",
    "shared_network": "Shared Network (No Segmentation)",
    "tokenized_only": "Tokenized API",
    "passthrough": "Pass-Through",
    "stored_processed": "Stored/Processed",
}


def _get_classification_display(classification: str | None) -> str:
    if not classification:
        return "Standard"
    return CLASSIFICATION_DISPLAY.get(classification, classification.replace("_", " ").title())


def generate_pdf(
    report_id: int,
    assessment_id: int,
    environment_type: str,
    scope_result: dict[str, Any],
) -> str | None:
    """
    Generate premium branded PCI DSS Readiness PDF (see pdf_report_builder).
    Returns file path or None on failure.
    """
    try:
        from app.services.pdf_report_builder import build_pci_readiness_pdf

        reports_dir = Path(settings.REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = reports_dir / f"report-{report_id}-assessment-{assessment_id}.pdf"
        ok = build_pci_readiness_pdf(
            report_id=report_id,
            assessment_id=assessment_id,
            environment_type=environment_type,
            scope_result=scope_result,
            output_path=file_path,
        )
        return str(file_path) if ok else None
    except Exception:
        return None


class ReportService:
    """Report generation and file handling."""

    @staticmethod
    async def get_or_404(db, report_id: int, user_id: int | None = None):
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select
        from app.models.report import Report

        result = await db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if not report:
            raise NotFoundError("Report", report_id)
        if user_id is not None and report.user_id != user_id:
            raise NotFoundError("Report", report_id)
        return report

    @staticmethod
    async def create_for_assessment(
        db,
        user_id: int,
        assessment_id: int,
        stripe_payment_id: str | None = None,
    ):
        from app.models.report import Report

        report = Report(
            user_id=user_id,
            assessment_id=assessment_id,
            stripe_payment_id=stripe_payment_id,
            status="pending",
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    @staticmethod
    async def create_pending_guest(
        db,
        assessment_id: int,
        stripe_payment_id: str | None = None,
    ):
        """Report before payment completes — user_id is set after Stripe webhook."""
        from app.models.report import Report

        report = Report(
            user_id=None,
            assessment_id=assessment_id,
            stripe_payment_id=stripe_payment_id,
            status="pending",
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    @staticmethod
    def generate_pdf_sync(report_id: int, assessment_id: int, environment_type: str, scope_result: dict) -> str | None:
        """Generate Phase 7 professional PDF report."""
        return generate_pdf(
            report_id=report_id,
            assessment_id=assessment_id,
            environment_type=environment_type,
            scope_result=scope_result,
        )
