"""
POS SAQ detection logic. Deterministic rules-based detection of likely SAQ path.
Never claims official compliance or definitive SAQ assignment.
"""
from typing import Literal

ConfidenceLevel = Literal["high", "medium", "low"]
LikelySAQ = Literal["B", "P2PE", "D", "Needs Review"]


def _normalize_answers(answers: dict[str, str]) -> dict[str, str]:
    """Normalize UI answer values to canonical form for rule evaluation."""
    norm = dict(answers)
    p2pe_raw = norm.get("p2pe", "")
    if p2pe_raw in ("p2pe_validated", "p2pe_encryption"):
        norm["p2pe"] = "yes"
    seg_raw = norm.get("network_segmentation", "")
    if seg_raw in ("yes_full", "yes_partial"):
        norm["network_segmentation"] = "yes"
    elif seg_raw in ("no_shared", "not_sure"):
        norm["network_segmentation"] = "no"
    return norm


def _is_p2pe_yes(answers: dict[str, str]) -> bool:
    """P2PE is PCI-listed or encryption (both reduce scope)."""
    v = answers.get("p2pe", "")
    return v in ("yes", "p2pe_validated", "p2pe_encryption")


def _is_pan_stored(answers: dict[str, str]) -> bool:
    """Full PAN stored electronically."""
    return answers.get("pos_q7", "") == "yes"


def _is_storage_after_auth_risky(answers: dict[str, str]) -> bool:
    """Temporarily or permanently stores card data after authorization."""
    return answers.get("pos_q8", "") in ("temporarily", "permanently")


def _is_decryption_in_environment(answers: dict[str, str]) -> bool:
    """Cardholder data decrypted within merchant environment."""
    return answers.get("pos_q13", "") == "yes"


def _is_pos_direct_processing(answers: dict[str, str]) -> bool:
    """POS software performs payment processing directly."""
    return answers.get("pos_q14", "") == "yes"


def _is_standalone_terminal(answers: dict[str, str]) -> bool:
    """Standalone payment terminal (narrow scope)."""
    return answers.get("terminal_type", "") == "standalone"


def _is_segmented(answers: dict[str, str]) -> bool:
    """Network is segmented (yes_full or yes_partial)."""
    v = answers.get("network_segmentation", "")
    return v in ("yes", "yes_full", "yes_partial")


def _is_encrypted_at_terminal(answers: dict[str, str]) -> bool:
    """Card data encrypted at terminal during capture."""
    return answers.get("pos_q12", "") == "yes"


def _is_integrated_or_broad(answers: dict[str, str]) -> bool:
    """Integrated POS, mobile, mixed, or self-checkout."""
    return answers.get("terminal_type", "") in ("integrated", "mobile", "mixed", "self_checkout")


def _has_weak_vendor_access(answers: dict[str, str]) -> bool:
    """Vendor remote access exists but controls are weak or unknown."""
    if answers.get("pos_q31", "") != "yes":
        return False
    restricted = answers.get("pos_q32", "") == "yes"
    rotated = answers.get("pos_q33", "") == "yes"
    disabled_when_not_needed = answers.get("pos_q34", "") == "yes"
    return not restricted or not rotated or not disabled_when_not_needed


def _count_not_sure_critical(answers: dict[str, str]) -> int:
    """Count 'not sure' / 'unsure' on critical questions."""
    critical_keys = [
        "pos_q7",   # PAN storage
        "pos_q8",   # storage after auth
        "p2pe",     # PCI-listed P2PE
        "pos_q12",  # encryption at terminal
        "pos_q13",  # decryption in environment
        "network_segmentation",
        "pos_q31",  # vendor remote access
        "pos_q14",  # direct payment processing
    ]
    unsure_values = ("not_sure", "unsure", "")
    count = 0
    for k in critical_keys:
        if answers.get(k, "") in unsure_values:
            count += 1
    return count


def _has_contradiction_p2pe_decrypt(answers: dict[str, str]) -> bool:
    """Says P2PE used but also decryption in environment (contradiction)."""
    return _is_p2pe_yes(answers) and _is_decryption_in_environment(answers)


def _has_broad_scope_risk(answers: dict[str, str]) -> bool:
    """Environment is broad or risky (D indicators)."""
    if _is_pan_stored(answers):
        return True
    if _is_storage_after_auth_risky(answers):
        return True
    if _is_decryption_in_environment(answers):
        return True
    if _is_pos_direct_processing(answers) and _is_integrated_or_broad(answers):
        return True
    if not _is_segmented(answers) and _is_integrated_or_broad(answers):
        return True
    if _has_weak_vendor_access(answers):
        return True
    return False


def _is_p2pe_candidate(answers: dict[str, str]) -> bool:
    """Strong SAQ P2PE indicators."""
    if not _is_p2pe_yes(answers):
        return False
    if _is_decryption_in_environment(answers):
        return False
    if _is_pan_stored(answers):
        return False
    if _is_storage_after_auth_risky(answers):
        return False
    if answers.get("pos_q12", "") == "no":
        return False
    if not _is_segmented(answers):
        return False
    return True


def _is_b_candidate(answers: dict[str, str]) -> bool:
    """Strong SAQ B indicators (narrow standalone, no storage, no decryption)."""
    if not _is_standalone_terminal(answers):
        return False
    if _is_pan_stored(answers):
        return False
    if _is_decryption_in_environment(answers):
        return False
    if _is_pos_direct_processing(answers):
        return False
    if _is_storage_after_auth_risky(answers):
        return False
    if _is_integrated_or_broad(answers):
        return False
    return True


def _get_information_gaps(answers: dict[str, str]) -> list[str]:
    """Identify critical questions answered 'not sure' or blank."""
    gaps = []
    labels = {
        "pos_q7": "Whether full PAN is stored electronically",
        "pos_q8": "Whether card data is stored after authorization",
        "p2pe": "Whether P2PE is PCI validated",
        "pos_q12": "Whether card data is encrypted at the terminal",
        "pos_q13": "Whether card data is decrypted in your environment",
        "network_segmentation": "Whether POS network is segmented",
        "pos_q31": "Whether vendor remote access exists and how it is controlled",
        "pos_q14": "Whether POS software processes payments directly",
        "pos_q34": "Whether vendor access is disabled when not needed",
    }
    unsure_values = ("not_sure", "unsure", "")
    for key, label in labels.items():
        if answers.get(key, "") in unsure_values:
            gaps.append(label)
    return gaps


def detect_pos_saq(answers: dict[str, str]) -> dict:
    """
    Detect likely POS SAQ path from assessment answers.
    Returns structured result for results page and report generation.
    Never claims official compliance or definitive SAQ assignment.
    """
    raw_p2pe = answers.get("p2pe", "")
    answers = _normalize_answers(answers)
    info_gaps = _get_information_gaps(answers)
    not_sure_count = _count_not_sure_critical(answers)
    has_contradiction = _has_contradiction_p2pe_decrypt(answers)
    has_d_risk = _has_broad_scope_risk(answers)

    # Priority 1: Strong D disqualifiers
    if has_d_risk:
        if has_contradiction:
            return _build_result(
                likely_saq="D",
                confidence="low",
                explanation=[
                    "Based on your answers, your environment indicates broader scope.",
                    "Some answers suggest storage or decryption of card data, or integrated processing with weak controls.",
                    "Contradictory answers (e.g., P2PE claimed but decryption in environment) lower confidence.",
                ],
                in_scope=[
                    "POS terminals",
                    "Back-office payment systems",
                    "Systems that store or process card data",
                    "Corporate network (if connected to POS)",
                ],
                out_scope=[],
                risk_flags=[
                    "Card data storage or decryption in merchant environment",
                    "Integrated POS with direct payment processing",
                    "Network segmentation concerns",
                    "Vendor remote access controls",
                ],
                recommendations=[
                    "Consider segmenting POS from corporate network",
                    "Document terminal management and data flow",
                    "Clarify P2PE and decryption architecture with your processor",
                    "Restrict and monitor vendor remote access",
                ],
                next_steps=[
                    "Review likely SAQ D eligibility against official PCI SSC criteria",
                    "Resolve contradictory answers with your payment processor",
                    "Engage your acquiring bank or QSA for final determination",
                ],
                information_gaps=info_gaps,
            )
        return _build_result(
            likely_saq="D",
            confidence="high" if not_sure_count <= 2 else "medium",
            explanation=[
                "Based on your answers, your environment indicates broader scope.",
                "Storage of full PAN, decryption in your environment, or integrated POS with direct processing typically requires SAQ D or ROC.",
            ],
            in_scope=[
                "POS terminals",
                "Back-office payment systems",
                "Systems that store or process card data",
                "Corporate network (if connected)",
            ],
            out_scope=[],
            risk_flags=[
                "Card data storage or decryption in merchant environment",
                "Integrated POS with direct payment processing",
                "Network segmentation",
            ],
            recommendations=[
                "Consider tokenization to reduce scope",
                "Segment POS from corporate network",
                "Document terminal management and data flow",
                "Engage QSA if full ROC is required",
            ],
            next_steps=[
                "Review likely SAQ D eligibility against official PCI SSC criteria",
                "Document all systems in cardholder data environment",
                "Confirm final SAQ selection with your compliance-enforcing entity",
            ],
            information_gaps=info_gaps,
        )

    # Priority 2: Contradiction without clear D risk -> Needs Review or D
    if has_contradiction:
        return _build_result(
            likely_saq="Needs Review",
            confidence="low",
            explanation=[
                "Your answers contain contradictions that affect scope determination.",
                "You indicated PCI-listed P2PE is used, but also that card data is decrypted within your environment.",
                "Final SAQ selection should be confirmed against official PCI SSC eligibility criteria.",
            ],
            in_scope=["POS terminals", "Payment-connected systems"],
            out_scope=[],
            risk_flags=["Contradictory answers on P2PE and decryption"],
            recommendations=[
                "Clarify with your payment processor whether P2PE is PCI validated",
                "Confirm where card data is decrypted (processor vs your environment)",
                "Document your exact data flow",
            ],
            next_steps=[
                "Resolve contradictions with your processor documentation",
                "Review official PCI SSC P2PE program requirements",
                "Confirm final SAQ with your acquiring bank or QSA",
            ],
            information_gaps=info_gaps,
        )

    # Priority 3: Strong P2PE pattern
    if _is_p2pe_candidate(answers):
        conf = "high" if not_sure_count <= 1 and raw_p2pe == "p2pe_validated" else "medium"
        return _build_result(
            likely_saq="P2PE",
            confidence=conf,
            explanation=[
                "Your answers indicate PCI-listed point-to-point encryption is used at the terminal.",
                "You reported no electronic storage of cardholder data and no decryption within your environment.",
            ],
            in_scope=[
                "POS terminals",
                "Payment-connected network segment",
                "Vendor support access controls",
            ],
            out_scope=[
                "Corporate office network (if segmented)",
                "Back-office systems not connected to the CDE",
            ],
            risk_flags=(
                ["Wireless usage should be confirmed as securely configured"]
                if answers.get("pos_q19") == "yes"
                else []
            ),
            recommendations=[
                "Maintain terminal inventory",
                "Confirm P2PE listing and supporting documentation",
                "Restrict and monitor remote vendor access",
            ],
            next_steps=[
                "Review likely SAQ P2PE eligibility against official criteria",
                "Gather segmentation and terminal management evidence",
                "Final SAQ selection should be confirmed with your compliance-enforcing entity",
            ],
            information_gaps=info_gaps,
        )

    # Priority 4: Strong B pattern
    if _is_b_candidate(answers):
        conf = "high" if not_sure_count <= 2 else "medium"
        return _build_result(
            likely_saq="B",
            confidence=conf,
            explanation=[
                "Based on your answers, you use standalone terminals with no electronic storage of full card data.",
                "No decryption in your environment and no integrated POS handling raw card data.",
            ],
            in_scope=[
                "POS terminals",
                "Payment-connected systems",
            ],
            out_scope=[
                "Corporate network (if properly isolated)",
            ],
            risk_flags=[],
            recommendations=[
                "Maintain terminal inventory",
                "Ensure receipts mask card numbers",
                "Document that no PAN is stored",
            ],
            next_steps=[
                "Review likely SAQ B eligibility against official criteria",
                "Confirm narrow card-present scope with your processor",
                "Final validation direction should be confirmed with your compliance-enforcing entity",
            ],
            information_gaps=info_gaps,
        )

    # Priority 5: Too many not sure -> D or Needs Review
    if not_sure_count >= 4:
        return _build_result(
            likely_saq="Needs Review",
            confidence="low",
            explanation=[
                "Several critical questions were answered 'Not sure' or left blank.",
                "Insufficient information to confidently suggest a SAQ path.",
            ],
            in_scope=["POS terminals", "Payment-connected systems"],
            out_scope=[],
            risk_flags=["Incomplete or uncertain answers on critical scope questions"],
            recommendations=[
                "Complete answers for PAN storage, P2PE status, and decryption location",
                "Document network segmentation",
                "Clarify vendor remote access controls",
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
            "Based on your answers, your environment does not clearly fit SAQ B or P2PE eligibility.",
            "When scope is unclear or environment is broad, SAQ D is often the default path.",
        ],
        in_scope=[
            "POS terminals",
            "Back-office payment systems",
            "Connected systems",
        ],
        out_scope=[],
        risk_flags=["Environment scope not clearly reduced"],
        recommendations=[
            "Document your exact payment flow and data handling",
            "Consider segmentation and P2PE to reduce scope",
            "Engage your processor or QSA for scope clarification",
        ],
        next_steps=[
            "Review SAQ D requirements",
            "Confirm final SAQ selection with your compliance-enforcing entity",
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
