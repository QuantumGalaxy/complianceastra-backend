"""
Payment Platform / Service Provider SAQ detection logic.
Deterministic rules for SAQ D (Service Provider) vs ROC.
Never claims official compliance.
"""


def _receives_card_data(answers: dict[str, str]) -> bool:
    """Platform receives cardholder data from merchants."""
    return answers.get("psp_q2", "") == "yes"


def _stores_card_data(answers: dict[str, str]) -> bool:
    """Platform stores cardholder data (encrypted or not)."""
    return answers.get("psp_q3", "") in ("yes_encrypted", "yes_unencrypted")


def _decrypts_card_data(answers: dict[str, str]) -> bool:
    """Platform decrypts cardholder data."""
    return answers.get("psp_q4", "") == "yes"


def _tokenizes(answers: dict[str, str]) -> bool:
    """Platform tokenizes card data."""
    return answers.get("psp_q5", "") == "yes"


def _processes_authorization(answers: dict[str, str]) -> bool:
    """Platform processes payment authorization requests."""
    return answers.get("psp_q9", "") == "yes"


def _has_merchant_apis(answers: dict[str, str]) -> bool:
    """Merchants connect through APIs."""
    return answers.get("psp_q7", "") == "yes"


def _get_information_gaps(answers: dict[str, str]) -> list[str]:
    """Identify critical questions answered 'not sure' or blank."""
    gaps = []
    labels = {
        "psp_q2": "Whether platform receives cardholder data from merchants",
        "psp_q3": "Whether system stores cardholder data",
        "psp_q4": "Whether system decrypts cardholder data",
        "psp_q5": "Whether platform tokenizes card data",
        "psp_q9": "Whether platform processes authorization requests",
    }
    for k, label in labels.items():
        if answers.get(k, "") in ("not_sure", "unsure", ""):
            gaps.append(label)
    return gaps


def detect_payment_platform_saq(answers: dict[str, str]) -> dict:
    """
    Detect likely validation path for payment platform / service provider.
    Returns: likely_saq, confidence, explanation, in_scope_items, out_scope_items,
    risk_flags, recommendations, next_steps, information_gaps.
    Never claims official compliance.
    """
    info_gaps = _get_information_gaps(answers)
    receives = _receives_card_data(answers)
    stores = _stores_card_data(answers)
    decrypts = _decrypts_card_data(answers)
    tokenizes = _tokenizes(answers)
    processes = _processes_authorization(answers)
    has_apis = _has_merchant_apis(answers)

    # Large-scale: receives + stores + processes + decrypts → ROC likely
    large_scale = receives and (stores or decrypts) and processes
    if large_scale:
        return _build_result(
            likely_saq="ROC (Report on Compliance)",
            confidence="high",
            explanation=[
                "Based on your answers, your platform receives, processes, and stores or decrypts cardholder data.",
                "Large-scale payment platform infrastructure typically requires a Report on Compliance (ROC) from a Qualified Security Assessor.",
            ],
            in_scope=[
                "Payment platform infrastructure",
                "API endpoints handling card data",
                "Systems that store or process cardholder data",
                "Database and storage systems",
            ],
            out_scope=[],
            risk_flags=[
                "Card data storage and processing",
                "Service provider scope",
            ],
            recommendations=[
                "Engage a Qualified Security Assessor (QSA) for ROC",
                "Document data flow architecture",
                "Implement and document security controls",
            ],
            next_steps=[
                "Confirm ROC requirement with your acquiring bank or card brands",
                "Final validation must be confirmed with a qualified security assessor",
            ],
            information_gaps=info_gaps,
        )

    # Stores or processes raw card data → SAQ D (Service Provider)
    if stores or decrypts or (receives and processes):
        return _build_result(
            likely_saq="SAQ D (Service Provider)",
            confidence="high",
            explanation=[
                "Based on your answers, your platform stores, processes, or transmits cardholder data.",
                "Service providers handling card data typically fall under SAQ D (Service Provider) or ROC.",
            ],
            in_scope=[
                "Payment platform infrastructure",
                "Systems that store, process, or transmit card data",
            ],
            out_scope=[],
            risk_flags=[
                "Card data handling",
                "Service provider scope",
            ],
            recommendations=[
                "Document data flow and security controls",
                "Consider tokenization to reduce scope where possible",
                "Engage QSA if full ROC is required",
            ],
            next_steps=[
                "Review SAQ D (Service Provider) requirements",
                "Final validation must be confirmed with your acquiring bank or a qualified security assessor",
            ],
            information_gaps=info_gaps,
        )

    # Tokenization only, no raw card data → SAQ D (Service Provider), medium confidence
    if tokenizes and not receives and not stores and not decrypts:
        return _build_result(
            likely_saq="SAQ D (Service Provider)",
            confidence="medium",
            explanation=[
                "Based on your answers, your platform handles tokenization but does not process raw card data.",
                "Tokenization services still fall under service provider scope and typically require SAQ D (Service Provider).",
            ],
            in_scope=[
                "Tokenization infrastructure",
                "API endpoints",
                "Token storage systems",
            ],
            out_scope=[
                "Systems that never handle card data",
            ],
            risk_flags=[
                "Token management",
                "API security",
            ],
            recommendations=[
                "Document token flow and ensure no PAN exposure",
                "Implement API security controls",
            ],
            next_steps=[
                "Review SAQ D (Service Provider) requirements for tokenization",
                "Final validation must be confirmed with your acquiring bank or a qualified security assessor",
            ],
            information_gaps=info_gaps,
        )

    # Default: SAQ D (Service Provider) - conservative for payment platforms
    return _build_result(
        likely_saq="SAQ D (Service Provider)",
        confidence="medium",
        explanation=[
            "Based on your answers, your platform operates as a payment service provider.",
            "Service providers typically require SAQ D (Service Provider) or ROC depending on scope.",
        ],
        in_scope=[
            "Payment platform infrastructure",
            "Systems handling payment data",
        ],
        out_scope=[],
        risk_flags=["Scope requires clarification"],
        recommendations=[
            "Document your exact data flow and card data handling",
            "Clarify with your acquiring bank or card brands",
        ],
        next_steps=[
            "Complete critical questions for accurate guidance",
            "Final validation must be confirmed with your acquiring bank or a qualified security assessor",
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
