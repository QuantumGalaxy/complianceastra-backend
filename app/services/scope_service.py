"""Phase 6: Compliance assessment engine. Rules engine with confidence scoring."""
from app.schemas.assessment import ScopeResult, RecommendationDetail
from app.services.pos_saq_logic import detect_pos_saq
from app.services.ecommerce_saq_logic import detect_ecommerce_saq
from app.services.payment_platform_saq_logic import detect_payment_platform_saq

# Risk flag keys -> human-readable labels
RISK_FLAG_LABELS: dict[str, str] = {
    "card_data_storage": "Card data storage",
    "encryption_at_rest": "Encryption at rest",
    "access_controls": "Access controls",
    "key_management": "Key management",
    "network_segmentation": "Network segmentation",
    "terminal_management": "Terminal management",
    "multi_location_scope": "Multi-location scope",
    "multi_tenant_isolation": "Multi-tenant isolation",
    "sub_processor_management": "Sub-processor management",
    "api_security": "API security",
    "data_flow_verification": "Verify data flow with your processor",
}


def _risk_areas_from_flags(flags: list[str]) -> list[str]:
    return [RISK_FLAG_LABELS.get(f, f) for f in flags]


def _recommendations_from_details(details: list[RecommendationDetail]) -> list[str]:
    return [d.action for d in sorted(details, key=lambda x: x.priority)]


def _confidence(
    base: int = 70,
    rule_bonus: int = 0,
    completeness_bonus: int = 0,
    ambiguity_penalty: int = 0,
    conflict_penalty: int = 0,
) -> int:
    score = base + rule_bonus + completeness_bonus - ambiguity_penalty - conflict_penalty
    return max(0, min(100, score))


class ScopeService:
    """Phase 6 rules engine for PCI DSS scope computation."""

    @staticmethod
    def compute_scope(environment_type: str, answers: dict[str, str]) -> ScopeResult:
        """
        Compute full scope result from answers.
        answers: dict mapping question_key -> answer_value
        """
        if environment_type == "ecommerce":
            return ScopeService._ecommerce_scope(answers)
        if environment_type == "pos":
            return ScopeService._pos_scope(answers)
        if environment_type == "payment_platform":
            return ScopeService._payment_platform_scope(answers)
        return ScopeService._default_scope(environment_type, answers)

    @staticmethod
    def _ecommerce_scope(answers: dict[str, str]) -> ScopeResult:
        """E-commerce scope: delegate to E-commerce SAQ detection logic for full result."""
        saq_result = detect_ecommerce_saq(answers)
        likely_saq = saq_result.get("likely_saq", "D")
        confidence = saq_result.get("confidence", "medium")
        explanation = saq_result.get("explanation", [])
        in_scope = saq_result.get("in_scope_items", [])
        out_scope = saq_result.get("out_scope_items", [])
        risk_flags = saq_result.get("risk_flags", [])
        recommendations = saq_result.get("recommendations", [])
        next_steps = saq_result.get("next_steps", [])
        information_gaps = saq_result.get("information_gaps", [])

        summary = explanation[0] if explanation else "Based on your answers, your likely validation direction is indicated below."
        scope_level = "reduced" if likely_saq in ("A", "A-EP") else ("expanded" if likely_saq == "D" else "standard")
        env_class = {
            "A": "redirect_only_checkout",
            "A-EP": "hosted_fields_checkout",
            "D": "card_data_storage",
            "Needs Review": "unknown",
        }.get(likely_saq, "unknown")
        conf_score = {"high": 85, "medium": 65, "low": 45}.get(confidence, 65)
        suggested_saq = f"SAQ {likely_saq}" if likely_saq in ("A", "A-EP", "D") else ("Needs Review" if likely_saq == "Needs Review" else "TBD")

        rec_details = [RecommendationDetail(priority=i + 1, action=r, rationale=None, category="ecommerce_saq") for i, r in enumerate(recommendations[:5])]

        return ScopeResult(
            summary=summary,
            in_scope=in_scope,
            out_of_scope=out_scope,
            risk_areas=risk_flags,
            recommendations=recommendations,
            scope_level=scope_level,
            environment_classification=env_class,
            confidence_score=conf_score,
            risk_flags=risk_flags,
            scope_insights=explanation[1:] if len(explanation) > 1 else [],
            recommendation_details=rec_details,
            suggested_saq=suggested_saq,
            next_steps=next_steps,
            likely_saq=likely_saq,
            confidence=confidence,
            explanation=explanation,
            information_gaps=information_gaps,
        )

    @staticmethod
    def _pos_scope(answers: dict[str, str]) -> ScopeResult:
        """POS scope: delegate to POS SAQ detection logic for full result."""
        saq_result = detect_pos_saq(answers)
        likely_saq = saq_result.get("likely_saq", "D")
        confidence = saq_result.get("confidence", "medium")
        explanation = saq_result.get("explanation", [])
        in_scope = saq_result.get("in_scope_items", [])
        out_scope = saq_result.get("out_scope_items", [])
        risk_flags = saq_result.get("risk_flags", [])
        recommendations = saq_result.get("recommendations", [])
        next_steps = saq_result.get("next_steps", [])
        information_gaps = saq_result.get("information_gaps", [])

        summary = explanation[0] if explanation else "Based on your answers, your likely validation direction is indicated below."
        scope_level = "reduced" if likely_saq in ("B", "P2PE") else ("expanded" if likely_saq == "D" else "standard")
        env_class = "p2pe_standalone" if likely_saq == "P2PE" else ("shared_network" if likely_saq == "D" else "integrated_pos")
        conf_score = {"high": 85, "medium": 65, "low": 45}.get(confidence, 65)
        suggested_saq = f"SAQ {likely_saq}" if likely_saq in ("B", "P2PE", "D") else ("Needs Review" if likely_saq == "Needs Review" else "TBD")

        rec_details = [RecommendationDetail(priority=i + 1, action=r, rationale=None, category="pos_saq") for i, r in enumerate(recommendations[:5])]

        return ScopeResult(
            summary=summary,
            in_scope=in_scope,
            out_of_scope=out_scope,
            risk_areas=risk_flags,
            recommendations=recommendations,
            scope_level=scope_level,
            environment_classification=env_class,
            confidence_score=conf_score,
            risk_flags=risk_flags,
            scope_insights=explanation[1:] if len(explanation) > 1 else [],
            recommendation_details=rec_details,
            suggested_saq=suggested_saq,
            next_steps=next_steps,
            likely_saq=likely_saq,
            confidence=confidence,
            explanation=explanation,
            information_gaps=information_gaps,
        )

    @staticmethod
    def _payment_platform_scope(answers: dict[str, str]) -> ScopeResult:
        """Payment platform scope: delegate to payment platform SAQ detection logic."""
        saq_result = detect_payment_platform_saq(answers)
        likely_saq = saq_result.get("likely_saq", "SAQ D (Service Provider)")
        confidence = saq_result.get("confidence", "medium")
        explanation = saq_result.get("explanation", [])
        in_scope = saq_result.get("in_scope_items", [])
        out_scope = saq_result.get("out_scope_items", [])
        risk_flags = saq_result.get("risk_flags", [])
        recommendations = saq_result.get("recommendations", [])
        next_steps = saq_result.get("next_steps", [])
        information_gaps = saq_result.get("information_gaps", [])

        summary = explanation[0] if explanation else "Based on your answers, your likely validation path is indicated below."
        scope_level = "expanded" if "ROC" in likely_saq else "standard"
        env_class = "stored_processed" if "ROC" in likely_saq else "tokenized_only"
        conf_score = {"high": 85, "medium": 65, "low": 45}.get(confidence, 65)

        rec_details = [RecommendationDetail(priority=i + 1, action=r, rationale=None, category="payment_platform_saq") for i, r in enumerate(recommendations[:5])]

        return ScopeResult(
            summary=summary,
            in_scope=in_scope,
            out_of_scope=out_scope,
            risk_areas=risk_flags,
            recommendations=recommendations,
            scope_level=scope_level,
            environment_classification=env_class,
            confidence_score=conf_score,
            risk_flags=risk_flags,
            scope_insights=explanation[1:] if len(explanation) > 1 else [],
            recommendation_details=rec_details,
            suggested_saq=likely_saq,
            next_steps=next_steps,
            likely_saq=likely_saq,
            confidence=confidence,
            explanation=explanation,
            information_gaps=information_gaps,
        )

    @staticmethod
    def _default_scope(environment_type: str, answers: dict[str, str]) -> ScopeResult:
        return ScopeResult(
            summary=f"Scope analysis for {environment_type}. Review your answers for guidance.",
            in_scope=["Systems handling payment data"],
            out_of_scope=[],
            risk_areas=["Document your environment"],
            recommendations=["Complete all questions for accurate scope"],
            scope_level="standard",
            environment_classification="unknown",
            confidence_score=_confidence(ambiguity_penalty=20),
            risk_flags=[],
            scope_insights=[],
            recommendation_details=[
                RecommendationDetail(priority=1, action="Complete all questions for accurate scope", rationale=None, category="assessment"),
            ],
            suggested_saq="TBD",
            next_steps=["Complete assessment"],
        )
