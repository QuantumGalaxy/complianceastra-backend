"""
E-commerce SAQ detection logic. Deterministic rules-based detection of likely SAQ path.
Never claims official compliance or definitive SAQ assignment.
Supports: SAQ A, SAQ A-EP, SAQ D
"""
from typing import Literal


def _is_redirect_only(answers: dict[str, str]) -> bool:
    """Customer redirected to payment provider page - SAQ A pattern."""
    return answers.get("ecom_q4", "") == "redirect"


def _is_embedded_or_iframe(answers: dict[str, str]) -> bool:
    """Embedded payment form or iframe - SAQ A-EP pattern."""
    return answers.get("ecom_q4", "") in ("embedded", "iframe")


def _is_merchant_hosted_form(answers: dict[str, str]) -> bool:
    """Merchant hosted payment form - SAQ D pattern."""
    return answers.get("ecom_q4", "") == "merchant_hosted"


def _website_receives_card_data(answers: dict[str, str]) -> bool:
    """Website ever receives raw card data."""
    return answers.get("ecom_q5", "") == "yes"


def _backend_processes_payment(answers: dict[str, str]) -> bool:
    """Backend server processes payment requests."""
    return answers.get("ecom_q6", "") == "yes"


def _stores_pan(answers: dict[str, str]) -> bool:
    """System stores full card numbers (PAN)."""
    return answers.get("ecom_q7", "") == "yes"


def _stores_after_auth(answers: dict[str, str]) -> bool:
    """Stores card data after authorization."""
    return answers.get("ecom_q8", "") in ("yes_temporarily", "yes_permanently")


def _payment_page_hosted_by_provider(answers: dict[str, str]) -> bool:
    """Payment page hosted by payment provider."""
    return answers.get("ecom_q10", "") == "yes"


def _count_not_sure_critical(answers: dict[str, str]) -> int:
    """Count 'not sure' on critical ecommerce questions."""
    critical = ["ecom_q4", "ecom_q5", "ecom_q6", "ecom_q7", "ecom_q8", "ecom_q10"]
    unsure = ("not_sure", "unsure", "")
    return sum(1 for k in critical if answers.get(k, "") in unsure)


def _get_information_gaps(answers: dict[str, str]) -> list[str]:
    """Identify critical questions answered 'not sure' or blank."""
    gaps = []
    labels = {
        "ecom_q4": "How customers enter card details",
        "ecom_q5": "Whether website receives raw card data",
        "ecom_q6": "Whether backend processes payment",
        "ecom_q7": "Whether full PAN is stored",
        "ecom_q8": "Whether card data is stored after authorization",
        "ecom_q10": "Whether payment page is hosted by provider",
    }
    for k, label in labels.items():
        if answers.get(k, "") in ("not_sure", "unsure", ""):
            gaps.append(label)
    return gaps


def detect_ecommerce_saq(answers: dict[str, str]) -> dict:
    """
    Detect likely E-commerce SAQ path from assessment answers.
    Returns: likely_saq, confidence, explanation, in_scope_items, out_scope_items,
    risk_flags, recommendations, next_steps, information_gaps.
    Never claims official compliance.
    """
    info_gaps = _get_information_gaps(answers)
    not_sure_count = _count_not_sure_critical(answers)

    # Strong SAQ D: merchant receives, processes, or stores card data
    if _website_receives_card_data(answers) or _backend_processes_payment(answers):
        return _build_result(
            likely_saq="D",
            confidence="high" if not_sure_count <= 2 else "medium",
            explanation=[
                "Based on your answers, your website or backend receives or processes card data.",
                "This typically requires SAQ D or ROC.",
            ],
            in_scope=[
                "E-commerce website",
                "Backend servers processing payment",
                "Systems that store or transmit card data",
            ],
            out_scope=[],
            risk_flags=[
                "Card data touches merchant systems",
                "Payment processing on merchant infrastructure",
            ],
            recommendations=[
                "Consider redirect or hosted fields to reduce scope",
                "Document exact data flow for assessor",
                "Engage QSA if full ROC is required",
            ],
            next_steps=[
                "Review SAQ D requirements",
                "Confirm final SAQ selection with your acquiring bank or PCI assessor",
            ],
            information_gaps=info_gaps,
        )

    if _stores_pan(answers) or _stores_after_auth(answers):
        return _build_result(
            likely_saq="D",
            confidence="high" if not_sure_count <= 2 else "medium",
            explanation=[
                "Based on your answers, your system stores card data.",
                "Storage of PAN or post-authorization data typically requires SAQ D.",
            ],
            in_scope=[
                "E-commerce website",
                "Systems storing card data",
                "Database and backup systems",
            ],
            out_scope=[],
            risk_flags=["Card data storage"],
            recommendations=[
                "Consider tokenization to reduce scope",
                "Document encryption and access controls",
                "Engage QSA if storing PAN",
            ],
            next_steps=[
                "Review SAQ D requirements",
                "Confirm final SAQ selection with your acquiring bank or PCI assessor",
            ],
            information_gaps=info_gaps,
        )

    if _is_merchant_hosted_form(answers):
        return _build_result(
            likely_saq="D",
            confidence="high",
            explanation=[
                "Based on your answers, you use a merchant-hosted payment form.",
                "Merchant-hosted forms typically receive card data and require SAQ D.",
            ],
            in_scope=[
                "E-commerce website",
                "Payment form hosting",
                "Payment integration configuration",
            ],
            out_scope=[],
            risk_flags=["Merchant-hosted payment form"],
            recommendations=[
                "Consider Stripe Elements, Braintree hosted fields, or redirect to reduce scope",
                "Document exact data flow",
            ],
            next_steps=[
                "Review SAQ D requirements",
                "Confirm final SAQ selection with your acquiring bank or PCI assessor",
            ],
            information_gaps=info_gaps,
        )

    # Strong SAQ A: redirect, no card data on merchant systems
    if _is_redirect_only(answers) and not _website_receives_card_data(answers):
        if _payment_page_hosted_by_provider(answers) or answers.get("ecom_q10", "") in ("", "not_sure"):
            conf = "high" if not_sure_count <= 1 else "medium"
            return _build_result(
                likely_saq="A",
                confidence=conf,
                explanation=[
                    "Your answers indicate customers are redirected to a payment provider hosted page.",
                    "Merchant systems do not process or store cardholder data.",
                ],
                in_scope=[
                    "E-commerce website",
                    "Payment integration configuration",
                ],
                out_scope=[
                    "Payment processing infrastructure",
                    "Card data storage systems",
                ],
                risk_flags=[],
                recommendations=[
                    "Maintain redirect flow; ensure no card data touches your servers",
                    "Confirm processor compliance status",
                ],
                next_steps=[
                    "Review likely SAQ A eligibility against official criteria",
                    "Final SAQ selection should be confirmed with your acquiring bank or PCI assessor",
                ],
                information_gaps=info_gaps,
            )

    # Strong SAQ A-EP: embedded/iframe, no storage
    if _is_embedded_or_iframe(answers) and not _website_receives_card_data(answers):
        conf = "high" if not_sure_count <= 1 else "medium"
        return _build_result(
            likely_saq="A-EP",
            confidence=conf,
            explanation=[
                "Your answers indicate payment fields are embedded via iframe or hosted fields.",
                "Merchant website hosts the checkout page but payment processor handles card data.",
            ],
            in_scope=[
                "E-commerce website",
                "Checkout page hosting",
                "Payment integration (JavaScript/iframe)",
            ],
            out_scope=[
                "Payment processing infrastructure",
                "Card data storage systems",
            ],
            risk_flags=[
                "Verify payment page scripts are from compliant provider",
                "Ensure no card data passes through merchant servers",
            ],
            recommendations=[
                "Maintain hosted fields; ensure scripts load from processor",
                "Document that no PAN touches your systems",
                "Verify WAF and script integrity controls",
            ],
            next_steps=[
                "Review likely SAQ A-EP eligibility against official criteria",
                "Final SAQ selection should be confirmed with your acquiring bank or PCI assessor",
            ],
            information_gaps=info_gaps,
        )

    # Too many not sure
    if not_sure_count >= 4:
        return _build_result(
            likely_saq="Needs Review",
            confidence="low",
            explanation=[
                "Several critical questions were answered 'Not sure' or left blank.",
                "Insufficient information to confidently suggest a SAQ path.",
            ],
            in_scope=["E-commerce website", "Payment integration"],
            out_scope=[],
            risk_flags=["Incomplete answers on critical scope questions"],
            recommendations=[
                "Complete answers for card entry method, data flow, and storage",
                "Document your exact payment architecture",
            ],
            next_steps=[
                "Provide complete answers for critical questions",
                "Review official PCI SSC eligibility criteria",
                "Consult your acquiring bank or QSA",
            ],
            information_gaps=info_gaps,
        )

    # Default: D (conservative when unclear)
    return _build_result(
        likely_saq="D",
        confidence="medium",
        explanation=[
            "Based on your answers, your environment does not clearly fit SAQ A or A-EP eligibility.",
            "When scope is unclear, SAQ D is often the default path.",
        ],
        in_scope=[
            "E-commerce website",
            "Payment integration",
            "Connected systems",
        ],
        out_scope=[],
        risk_flags=["Environment scope not clearly reduced"],
        recommendations=[
            "Document your exact payment flow and data handling",
            "Consider redirect or hosted fields to reduce scope",
            "Engage your processor or QSA for scope clarification",
        ],
        next_steps=[
            "Review SAQ D requirements",
            "Confirm final SAQ selection with your acquiring bank or PCI assessor",
        ],
        information_gaps=info_gaps,
    )


def _build_result(
    *,
    likely_saq: str,
    confidence: str,
    explanation: list[str],
    in_scope: list[str],
    out_scope: list[str],
    risk_flags: list[str],
    recommendations: list[str],
    next_steps: list[str],
    information_gaps: list[str],
) -> dict:
    """Build the structured result dict."""
    return {
        "likely_saq": likely_saq,
        "confidence": confidence,
        "explanation": explanation,
        "in_scope_items": in_scope,
        "out_scope_items": out_scope,
        "risk_flags": risk_flags,
        "recommendations": recommendations,
        "next_steps": next_steps,
        "information_gaps": information_gaps,
    }
