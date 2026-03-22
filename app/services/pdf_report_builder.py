"""
Premium PCI DSS Readiness Report PDF layout (ReportLab).
Branded headers/footers, section bars, summary cards, tables, risk badges.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

# Display helpers (aligned with report_service / frontend scope_result)
ENV_DISPLAY = {
    "ecommerce": "Ecommerce",
    "pos": "POS",
    "payment_platform": "Payment Platform",
    "moto": "MOTO",
}
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

# Brand palette
NAVY = "#0c1929"
NAVY_TEXT = "#0f172a"
GREEN = "#059669"
GREEN_DARK = "#047857"
GREEN_LIGHT_BG = "#ecfdf5"
GREEN_MUTED = "#d1fae5"
SLATE_BG = "#f8fafc"
SLATE_BORDER = "#e2e8f0"
SLATE_MUTED = "#64748b"
WHITE = "#ffffff"

RISK_BADGE = {
    "high": ("#b91c1c", "#fef2f2"),
    "medium": ("#b45309", "#fffbeb"),
    "low": ("#047857", "#ecfdf5"),
}


def _esc(text: str | None) -> str:
    if not text:
        return ""
    return html.escape(str(text).replace("\n", " "))


def _risk_badge_colors(level: str | None) -> tuple[str, str]:
    key = (level or "medium").lower().strip()
    return RISK_BADGE.get(key, RISK_BADGE["medium"])


def _suggested_saq_display(scope_result: dict) -> str:
    likely = scope_result.get("likely_saq")
    suggested = scope_result.get("suggested_saq", "TBD")
    if likely:
        return f"SAQ {likely}" if str(likely) in ("B", "P2PE", "D", "A", "A-EP", "C", "C-VT") else str(likely)
    return str(suggested)


def _build_executive_summary(scope_result: dict, environment_type: str) -> str:
    summary = scope_result.get("summary", "")
    scope_level = scope_result.get("scope_level", "standard")
    suggested_saq = scope_result.get("suggested_saq", "TBD")
    likely_saq = scope_result.get("likely_saq")
    env_name = ENV_DISPLAY.get(environment_type, environment_type)

    lines = [
        f"This report summarizes the PCI DSS scope analysis for your {env_name.lower()} payment environment. "
        f"Based on your assessment answers, your scope level is <b>{_esc(scope_level)}</b>.",
        "",
        _esc(summary),
        "",
    ]
    if environment_type in ("pos", "ecommerce", "payment_platform") and likely_saq:
        saq_label = f"SAQ {likely_saq}" if likely_saq in ("B", "P2PE", "D", "A", "A-EP") else str(likely_saq)
        lines.append(
            f"Likely validation direction: <b>{_esc(saq_label)}</b>. "
            "This is guidance only; final SAQ selection should be confirmed against official PCI SSC eligibility criteria and your compliance-enforcing entity."
        )
    else:
        lines.append(
            f"Suggested compliance path: <b>{_esc(str(suggested_saq))}</b>. "
            "This report provides guidance only; final determination rests with your acquiring bank or qualified security assessor."
        )
    return "<br/>".join(lines)


def _header_footer_canvas(canvas, doc) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor

    page_width, page_height = letter
    canvas.saveState()
    # Top accent bar
    canvas.setFillColor(HexColor(GREEN))
    canvas.rect(0, page_height - 0.12 * inch, page_width, 0.12 * inch, stroke=0, fill=1)
    # Header row
    canvas.setFillColor(HexColor(GREEN_DARK))
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(0.75 * inch, page_height - 0.42 * inch, "ComplianceAstra")
    canvas.setFillColor(HexColor(SLATE_MUTED))
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        page_width - 0.75 * inch,
        page_height - 0.4 * inch,
        "PCI DSS Readiness Report",
    )
    # Footer line
    canvas.setStrokeColor(HexColor(SLATE_BORDER))
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.62 * inch, page_width - 0.75 * inch, 0.62 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(HexColor(SLATE_MUTED))
    year = datetime.utcnow().year
    canvas.drawString(
        0.75 * inch,
        0.48 * inch,
        f"© {year} Dama AI LLC. All rights reserved.",
    )
    canvas.drawCentredString(
        page_width / 2,
        0.35 * inch,
        "Guidance only — not a certification or audit",
    )
    num = canvas.getPageNumber()
    canvas.drawRightString(page_width - 0.75 * inch, 0.48 * inch, f"Page {num}")
    canvas.restoreState()


def _section_bar(title: str, width: float) -> Any:
    """Green bar + navy title (ReportLab Table)."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Table, TableStyle

    bar_style = ParagraphStyle(
        name="SecBar",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor(NAVY_TEXT),
        leading=14,
        leftIndent=8,
    )
    inner = Table(
        [[Paragraph(_esc(title), bar_style)]],
        colWidths=[width],
        rowHeights=[0.35 * inch],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(GREEN_LIGHT_BG)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("LINEABOVE", (0, 0), (-1, -1), 4, colors.HexColor(GREEN)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return inner


def _summary_cards_table(
    suggested_saq: str,
    scope_level: str,
    risk_level: str,
    confidence_score: str | None,
    col_width: float,
) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    fg, bg = _risk_badge_colors(risk_level)
    lbl = ParagraphStyle(name="CardLbl", fontSize=8, textColor=colors.HexColor(SLATE_MUTED), leading=10)
    val = ParagraphStyle(name="CardVal", fontSize=11, textColor=colors.HexColor(NAVY_TEXT), leading=13, fontName="Helvetica-Bold")
    risk_lbl = ParagraphStyle(name="RLbl", parent=lbl)
    risk_val = ParagraphStyle(name="RVal", fontSize=11, leading=13, fontName="Helvetica-Bold", textColor=colors.HexColor(fg))

    cells = [
        [
            Paragraph("Suggested SAQ", lbl),
            Paragraph("Scope level", lbl),
        ],
        [
            Paragraph(_esc(suggested_saq), val),
            Paragraph(_esc(scope_level), val),
        ],
        [
            Paragraph("Risk level", risk_lbl),
            Paragraph("Confidence score", lbl),
        ],
        [
            Paragraph(_esc(str(risk_level or "Medium").title()), risk_val),
            Paragraph(_esc(confidence_score or "—"), val),
        ],
    ]
    t = Table(cells, colWidths=[col_width / 2 - 6, col_width / 2 - 6], hAlign="CENTER")
    ts = [
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SLATE_BG)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(SLATE_BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 3), (0, 3), colors.HexColor(bg)),
    ]
    t.setStyle(TableStyle(ts))
    return t


def _list_to_table_rows(items: list[str], col_header: str) -> list[list[str]]:
    rows = [[col_header, "Detail"]]
    for i, item in enumerate(items, 1):
        rows.append([str(i), _esc(item)])
    return rows


def build_pci_readiness_pdf(
    report_id: int,
    assessment_id: int,
    environment_type: str,
    scope_result: dict[str, Any],
    output_path: Path,
) -> bool:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=1.05 * inch,
            bottomMargin=0.85 * inch,
            title="PCI DSS Readiness Report",
            onFirstPage=_header_footer_canvas,
            onLaterPages=_header_footer_canvas,
        )
        styles = getSampleStyleSheet()
        full_width = letter[0] - 1.5 * inch

        cover_title = ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=28,
            textColor=colors.HexColor(NAVY),
            spaceAfter=8,
            alignment=1,
            fontName="Helvetica-Bold",
        )
        cover_sub = ParagraphStyle(
            name="CoverSub",
            fontSize=11,
            textColor=colors.HexColor(SLATE_MUTED),
            alignment=1,
            spaceAfter=4,
        )
        body = ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor(NAVY_TEXT),
            spaceAfter=8,
        )
        small = ParagraphStyle(
            name="Small",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor(SLATE_MUTED),
        )

        story: list[Any] = []

        # --- Page 1: Cover + Executive summary + cards ---
        story.append(Spacer(1, 0.35 * inch))
        story.append(
            Paragraph(
                '<font color="#059669" face="Helvetica-Bold" size="14">ComplianceAstra</font>',
                ParagraphStyle(name="Logo", alignment=1, spaceAfter=6),
            )
        )
        story.append(Paragraph("PCI DSS Readiness Report", cover_title))
        story.append(
            Paragraph(
                f"Generated {_esc(datetime.utcnow().strftime('%B %d, %Y'))} · UTC",
                cover_sub,
            )
        )
        story.append(
            Paragraph(
                f"Report #{report_id} · Assessment #{assessment_id}",
                cover_sub,
            )
        )
        story.append(Spacer(1, 0.35 * inch))

        story.append(_section_bar("Executive Summary", full_width))
        story.append(Spacer(1, 0.12 * inch))
        exec_html = _build_executive_summary(scope_result, environment_type)
        story.append(Paragraph(exec_html, body))
        story.append(Spacer(1, 0.25 * inch))

        story.append(_section_bar("Key metrics", full_width))
        story.append(Spacer(1, 0.12 * inch))
        risk_for_badge = scope_result.get("confidence") or "medium"
        if isinstance(risk_for_badge, str):
            risk_for_badge = risk_for_badge.strip()
        conf_score = scope_result.get("confidence_score")
        conf_str = f"{conf_score}%" if conf_score is not None else None
        story.append(
            _summary_cards_table(
                suggested_saq=_suggested_saq_display(scope_result),
                scope_level=str(scope_result.get("scope_level", "standard")),
                risk_level=str(risk_for_badge),
                confidence_score=conf_str,
                col_width=full_width,
            )
        )

        story.append(PageBreak())

        # --- Page 2: Scope analysis ---
        story.append(_section_bar("Scope Analysis", full_width))
        story.append(Spacer(1, 0.15 * inch))

        story.append(
            Paragraph(
                f"<b>Environment:</b> {_esc(ENV_DISPLAY.get(environment_type, environment_type))} · "
                f"<b>Classification:</b> {_esc(_get_classification_display(scope_result.get('environment_classification')))}",
                body,
            )
        )
        story.append(Spacer(1, 0.12 * inch))

        in_scope = scope_result.get("in_scope") or []
        out_scope = scope_result.get("out_of_scope") or []

        in_rows = (
            _list_to_table_rows([str(x) for x in in_scope], "#")
            if in_scope
            else [["#", "Detail"], ["—", "No items listed"]]
        )
        tin = Table(in_rows, colWidths=[0.45 * inch, full_width - 0.45 * inch])
        tin.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN_DARK)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(GREEN_LIGHT_BG)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(GREEN)),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(Paragraph("<b>In scope</b>", ParagraphStyle(name="BoxLbl", parent=body, fontSize=10, textColor=colors.HexColor(NAVY))))
        story.append(Spacer(1, 0.06 * inch))
        story.append(tin)
        story.append(Spacer(1, 0.2 * inch))

        out_rows = (
            _list_to_table_rows([str(x) for x in out_scope], "#")
            if out_scope
            else [["#", "Detail"], ["—", "No items listed"]]
        )
        tout = Table(out_rows, colWidths=[0.45 * inch, full_width - 0.45 * inch])
        tout.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY_TEXT)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor(SLATE_BG)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(SLATE_BORDER)),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(Paragraph("<b>Out of scope</b>", ParagraphStyle(name="BoxLbl2", parent=body, fontSize=10, textColor=colors.HexColor(NAVY))))
        story.append(Spacer(1, 0.06 * inch))
        story.append(tout)
        story.append(Spacer(1, 0.2 * inch))

        insights = scope_result.get("scope_insights") or []
        if insights:
            story.append(_section_bar("Key insights", full_width))
            story.append(Spacer(1, 0.1 * inch))
            ir = [["#", "Insight"]]
            for i, item in enumerate(insights, 1):
                ir.append([str(i), _esc(str(item))])
            ti = Table(ir, colWidths=[0.4 * inch, full_width - 0.4 * inch])
            ti.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN_MUTED)),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(SLATE_BG)]),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(ti)
            story.append(Spacer(1, 0.2 * inch))

        explanation = scope_result.get("explanation") or []
        env_ok = environment_type in ("pos", "ecommerce", "payment_platform")
        if explanation and env_ok:
            story.append(_section_bar("Analysis detail", full_width))
            story.append(Spacer(1, 0.1 * inch))
            er = [["#", "Point"]]
            for i, item in enumerate(explanation, 1):
                er.append([str(i), _esc(str(item))])
            te = Table(er, colWidths=[0.4 * inch, full_width - 0.4 * inch])
            te.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(SLATE_BG)),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(te)
            story.append(Spacer(1, 0.2 * inch))

        story.append(_section_bar("Risk findings", full_width))
        story.append(Spacer(1, 0.12 * inch))
        risk_areas = scope_result.get("risk_areas") or []
        if risk_areas:
            sev_para_style = ParagraphStyle(
                name="RiskSevCell",
                fontSize=9,
                leading=12,
                fontName="Helvetica-Bold",
            )
            rr = [["#", "Risk area", "Level", "Notes"]]
            for i, r in enumerate(risk_areas, 1):
                sev = "High" if any(
                    k in str(r).lower() for k in ("storage", "segmentation", "pan", "transmit")
                ) else "Medium"
                fg, _bg = _risk_badge_colors(sev.lower())
                sev_cell = Paragraph(
                    f'<font color="{fg}"><b>{_esc(sev)}</b></font>',
                    sev_para_style,
                )
                rr.append(
                    [
                        str(i),
                        Paragraph(_esc(str(r)), ParagraphStyle(name=f"Rk{i}", parent=body, fontSize=9, leading=12)),
                        sev_cell,
                        Paragraph("Review controls in this area", ParagraphStyle(name=f"Rn{i}", parent=body, fontSize=9)),
                    ]
                )
            tr = Table(rr, colWidths=[0.35 * inch, 2.4 * inch, 0.95 * inch, 2.3 * inch])
            tr.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(SLATE_BG)]),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(tr)
        else:
            story.append(
                Paragraph(
                    "No additional risk areas were flagged from your answers. Continue validating controls with your acquirer or QSA.",
                    body,
                )
            )

        story.append(PageBreak())

        # --- Page 3: Recommendations, next steps, disclaimer ---
        story.append(_section_bar("Requirement context", full_width))
        story.append(Spacer(1, 0.12 * inch))
        suggested_saq = scope_result.get("suggested_saq", "TBD")
        req_text = (
            f"Based on your <b>{_esc(scope_result.get('scope_level', 'standard'))}</b> scope, "
            "PCI DSS requirement areas likely in scope include secure network (Req 1), access control (Req 7–8), "
            "monitoring (Req 10), and security policies (Req 12). "
            f"Your suggested path (<b>{_esc(str(suggested_saq))}</b>) determines the applicable control set."
        )
        story.append(Paragraph(req_text, body))
        story.append(Spacer(1, 0.22 * inch))

        story.append(_section_bar("Recommended actions", full_width))
        story.append(Spacer(1, 0.12 * inch))
        rec_details = scope_result.get("recommendation_details") or []
        if rec_details:
            rd = [["Priority", "Action", "Rationale"]]
            for r in sorted(rec_details, key=lambda x: x.get("priority", 0)):
                rd.append(
                    [
                        str(r.get("priority", "")),
                        _esc(str(r.get("action", ""))),
                        _esc(str(r.get("rationale") or "—")),
                    ]
                )
            trec = Table(rd, colWidths=[0.55 * inch, 2.65 * inch, 2.8 * inch])
            trec.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN_DARK)),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(GREEN_LIGHT_BG)]),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(trec)
        else:
            recs = scope_result.get("recommendations") or []
            if recs:
                rrows = [["#", "Recommendation"]]
                for i, item in enumerate(recs, 1):
                    rrows.append([str(i), _esc(str(item))])
                trc = Table(rrows, colWidths=[0.4 * inch, full_width - 0.4 * inch])
                trc.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN_DARK)),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ]
                    )
                )
                story.append(trc)
            else:
                story.append(Paragraph("No specific recommendations beyond the scope analysis above.", body))

        next_steps = scope_result.get("next_steps") or []
        if next_steps:
            story.append(Spacer(1, 0.22 * inch))
            story.append(_section_bar("Next steps", full_width))
            story.append(Spacer(1, 0.12 * inch))
            ns = [["Step", "Action"]]
            for i, item in enumerate(next_steps, 1):
                ns.append([str(i), _esc(str(item))])
            tns = Table(ns, colWidths=[0.45 * inch, full_width - 0.45 * inch])
            tns.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(SLATE_BG)]),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(SLATE_BORDER)),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(tns)

        information_gaps = scope_result.get("information_gaps") or []
        if information_gaps and environment_type in ("pos", "ecommerce", "payment_platform"):
            story.append(Spacer(1, 0.2 * inch))
            story.append(_section_bar("Information gaps", full_width))
            story.append(Spacer(1, 0.08 * inch))
            story.append(
                Paragraph(
                    "Items answered &quot;Not sure&quot; or left blank — clarifying these may improve accuracy.",
                    small,
                )
            )
            story.append(Spacer(1, 0.08 * inch))
            gr = [["#", "Gap"]]
            for i, item in enumerate(information_gaps, 1):
                gr.append([str(i), _esc(str(item))])
            tg = Table(gr, colWidths=[0.4 * inch, full_width - 0.4 * inch])
            tg.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef3c7")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fcd34d")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(SLATE_BORDER)),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(tg)

        story.append(Spacer(1, 0.28 * inch))
        disc_box = Table(
            [
                [
                    Paragraph(
                        "<b>Disclaimer</b><br/><br/>"
                        "This report provides guidance and readiness insights only. It does not constitute a compliance certification or audit. "
                        "Final compliance validation depends on your acquiring bank, payment processor, or qualified security assessor (QSA) where applicable. "
                        "Dama AI LLC is not responsible for decisions made based on this report.",
                        ParagraphStyle(
                            name="Disc",
                            fontSize=8.5,
                            leading=13,
                            textColor=colors.HexColor(SLATE_MUTED),
                        ),
                    )
                ]
            ],
            colWidths=[full_width],
        )
        disc_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SLATE_BG)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(SLATE_BORDER)),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(disc_box)

        doc.build(story)
        return True
    except Exception:
        import logging

        logging.getLogger(__name__).exception("PDF build failed")
        return False
