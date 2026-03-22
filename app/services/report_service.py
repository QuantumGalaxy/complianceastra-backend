"""Phase 7: Professional paid report generation and storage."""
import os
from datetime import datetime
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


def _build_executive_summary(scope_result: dict, environment_type: str) -> str:
    """Generate 2-3 paragraph executive summary."""
    summary = scope_result.get("summary", "")
    scope_level = scope_result.get("scope_level", "standard")
    suggested_saq = scope_result.get("suggested_saq", "TBD")
    likely_saq = scope_result.get("likely_saq")
    env_name = ENV_DISPLAY.get(environment_type, environment_type)

    lines = [
        f"This report summarizes the PCI DSS scope analysis for your {env_name.lower()} payment environment. "
        f"Based on your assessment answers, your scope level is {scope_level}.",
        "",
        summary,
        "",
    ]
    if environment_type in ("pos", "ecommerce", "payment_platform") and likely_saq:
        saq_label = f"SAQ {likely_saq}" if likely_saq in ("B", "P2PE", "D", "A", "A-EP") else likely_saq
        lines.append(
            f"Likely validation direction: {saq_label}. "
            "This is guidance only; final SAQ selection should be confirmed against official PCI SSC eligibility criteria and your compliance-enforcing entity."
        )
    else:
        lines.append(
            f"Suggested compliance path: {suggested_saq}. "
            "This report provides guidance only; final determination rests with your acquiring bank or qualified security assessor."
        )
    return "\n".join(lines)


def generate_pdf(
    report_id: int,
    assessment_id: int,
    environment_type: str,
    scope_result: dict[str, Any],
) -> str | None:
    """
    Generate professional consultant-quality PDF report.
    Returns file path or None on failure.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )

        reports_dir = Path(settings.REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = reports_dir / f"report-{report_id}-assessment-{assessment_id}.pdf"

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=letter,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=1.25 * inch,
            bottomMargin=1.25 * inch,
        )
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontSize=18,
            spaceAfter=6,
            textColor=colors.HexColor("#0f172a"),
        )
        h1_style = ParagraphStyle(
            name="ReportH1",
            parent=styles["Heading1"],
            fontSize=14,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#0f172a"),
        )
        h2_style = ParagraphStyle(
            name="ReportH2",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
            textColor=colors.HexColor("#334155"),
        )
        body_style = ParagraphStyle(
            name="ReportBody",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=6,
            leading=14,
        )
        small_style = ParagraphStyle(
            name="ReportSmall",
            parent=styles["Normal"],
            fontSize=9,
            spaceAfter=4,
            textColor=colors.HexColor("#64748b"),
        )

        story = []

        # --- Cover / Header ---
        story.append(Paragraph("ComplianceAstra", small_style))
        story.append(Paragraph("PCI DSS Readiness Report", title_style))
        story.append(Spacer(1, 0.15 * inch))
        story.append(
            Paragraph(
                f"Report ID: {report_id} | Assessment ID: {assessment_id}",
                small_style,
            )
        )
        story.append(
            Paragraph(
                f"Generated: {datetime.utcnow().strftime('%B %d, %Y at %H:%M')} UTC",
                small_style,
            )
        )
        story.append(Spacer(1, 0.4 * inch))

        # --- Executive Summary ---
        story.append(Paragraph("Executive Summary", h1_style))
        exec_summary = _build_executive_summary(scope_result, environment_type)
        for para in exec_summary.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.replace("\n", " "), body_style))
        story.append(Spacer(1, 0.3 * inch))

        # --- 1. Environment Summary ---
        story.append(Paragraph("1. Environment Summary", h1_style))
        classification = scope_result.get("environment_classification")
        suggested_saq = scope_result.get("suggested_saq", "TBD")
        likely_saq = scope_result.get("likely_saq")
        confidence_level = scope_result.get("confidence")
        env_data = [
            ["Environment Type", ENV_DISPLAY.get(environment_type, environment_type)],
            ["Classification", _get_classification_display(classification)],
            ["Scope Level", scope_result.get("scope_level", "N/A")],
            ["Suggested Path", suggested_saq],
        ]
        if likely_saq and environment_type in ("pos", "ecommerce", "payment_platform"):
            label = "Likely Validation Path" if environment_type == "payment_platform" else "Likely SAQ Path"
            env_data.append([label, f"SAQ {likely_saq}" if likely_saq in ("B", "P2PE", "D", "A", "A-EP") else likely_saq])
        if confidence_level and environment_type in ("pos", "ecommerce", "payment_platform"):
            env_data.append(["Confidence", confidence_level.capitalize()])
        if scope_result.get("confidence_score") is not None:
            env_data.append(["Confidence Score", f"{scope_result['confidence_score']}%"])
        t = Table(env_data, colWidths=[2 * inch, 4 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.25 * inch))

        # --- 2. Scope Analysis ---
        story.append(Paragraph("2. Scope Analysis", h1_style))
        story.append(Paragraph(scope_result.get("summary", ""), body_style))
        explanation = scope_result.get("explanation", [])
        if explanation and environment_type in ("pos", "ecommerce", "payment_platform"):
            story.append(Spacer(1, 0.1 * inch))
            for item in explanation:
                story.append(Paragraph(f"• {item}", body_style))
        story.append(Spacer(1, 0.15 * inch))

        story.append(Paragraph("In Scope", h2_style))
        in_scope = scope_result.get("in_scope", [])
        if in_scope:
            for item in in_scope:
                story.append(Paragraph(f"• {item}", body_style))
        else:
            story.append(Paragraph("—", body_style))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph("Out of Scope", h2_style))
        out_scope = scope_result.get("out_of_scope", [])
        if out_scope:
            for item in out_scope:
                story.append(Paragraph(f"• {item}", body_style))
        else:
            story.append(Paragraph("—", body_style))

        scope_insights = scope_result.get("scope_insights", [])
        if scope_insights:
            story.append(Spacer(1, 0.15 * inch))
            story.append(Paragraph("Key Insights", h2_style))
            for item in scope_insights:
                story.append(Paragraph(f"• {item}", body_style))
        story.append(Spacer(1, 0.3 * inch))

        # --- 3. Risk Findings ---
        story.append(Paragraph("3. Risk Findings", h1_style))
        risk_areas = scope_result.get("risk_areas", [])
        if risk_areas:
            risk_data = [["Risk Area", "Severity", "Notes"]]
            for r in risk_areas:
                severity = "High" if "storage" in r.lower() or "segmentation" in r.lower() else "Medium"
                risk_data.append([r, severity, "Review controls in this area"])
            t2 = Table(risk_data, colWidths=[2.2 * inch, 1.2 * inch, 2.6 * inch])
            t2.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ]
                )
            )
            story.append(t2)
        else:
            story.append(Paragraph("No critical risk areas identified based on your answers.", body_style))
        story.append(Spacer(1, 0.3 * inch))

        # --- 4. Requirement Insights ---
        story.append(Paragraph("4. Requirement Insights", h1_style))
        req_text = (
            f"Based on your {scope_result.get('scope_level', 'standard')} scope, "
            "the following PCI DSS requirement areas are likely in scope: "
            "secure network (Req 1), access control (Req 7, 8), monitoring (Req 10), "
            "and policies (Req 12). "
            f"Your suggested path ({suggested_saq}) determines the exact control set. "
            "Consult your acquiring bank or QSA for final requirement mapping."
        )
        story.append(Paragraph(req_text, body_style))
        story.append(Spacer(1, 0.3 * inch))

        # --- 5. Recommended Actions ---
        story.append(Paragraph("5. Recommended Actions", h1_style))
        rec_details = scope_result.get("recommendation_details", [])
        if rec_details:
            rec_data = [["Priority", "Action", "Rationale"]]
            for r in sorted(rec_details, key=lambda x: x.get("priority", 0)):
                rec_data.append([
                    str(r.get("priority", "")),
                    r.get("action", ""),
                    r.get("rationale") or "—",
                ])
            t3 = Table(rec_data, colWidths=[0.6 * inch, 2.8 * inch, 2.6 * inch])
            t3.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#047857")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ]
                )
            )
            story.append(t3)
        else:
            recs = scope_result.get("recommendations", [])
            for i, item in enumerate(recs, 1):
                story.append(Paragraph(f"{i}. {item}", body_style))

        next_steps = scope_result.get("next_steps", [])
        if next_steps:
            story.append(Spacer(1, 0.15 * inch))
            story.append(Paragraph("Next Steps", h2_style))
            for item in next_steps:
                story.append(Paragraph(f"• {item}", body_style))

        information_gaps = scope_result.get("information_gaps", [])
        if information_gaps and environment_type in ("pos", "ecommerce", "payment_platform"):
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph("Information Gaps", h2_style))
            story.append(
                Paragraph(
                    "The following items were answered 'Not sure' or left blank. Clarifying these may improve the accuracy of your likely SAQ path.",
                    small_style,
                )
            )
            for item in information_gaps:
                story.append(Paragraph(f"• {item}", body_style))
        story.append(Spacer(1, 0.4 * inch))

        # --- Appendix: Disclaimer ---
        story.append(Paragraph("Appendix: Disclaimer", h1_style))
        disclaimer = (
            "This report provides guidance and readiness insights only. "
            "It does not constitute a compliance certification or audit. "
            "Final compliance validation depends on your acquiring bank, payment processor, "
            "or qualified security assessor (QSA) where applicable. "
            "ComplianceAstra LLC is not responsible for decisions made based on this report."
        )
        story.append(Paragraph(disclaimer, small_style))

        doc.build(story)
        return str(file_path)
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
