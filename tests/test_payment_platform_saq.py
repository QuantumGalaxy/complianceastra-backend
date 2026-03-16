"""
Tests for Payment Platform SAQ detection logic.
"""
import pytest

from app.services.payment_platform_saq_logic import detect_payment_platform_saq
from app.services.scope_service import ScopeService


def test_case1_gateway_storing_pan():
    """Case 1: Gateway storing PAN -> SAQ D (Service Provider)."""
    answers = {
        "psp_q2": "yes",
        "psp_q3": "yes_encrypted",
        "psp_q4": "yes",
        "psp_q9": "yes",
    }
    result = detect_payment_platform_saq(answers)
    assert "SAQ D (Service Provider)" in result["likely_saq"] or "ROC" in result["likely_saq"]
    assert result["confidence"] in ("high", "medium")


def test_case2_payment_api_tokenization():
    """Case 2: Payment API with tokenization -> SAQ D (Service Provider)."""
    answers = {
        "psp_q2": "no",
        "psp_q3": "no",
        "psp_q4": "no",
        "psp_q5": "yes",
    }
    result = detect_payment_platform_saq(answers)
    assert "SAQ D (Service Provider)" in result["likely_saq"]
    assert result["confidence"] == "medium"


def test_case3_large_processor_roc():
    """Case 3: Large payment processor infrastructure -> ROC likely required."""
    answers = {
        "psp_q2": "yes",
        "psp_q3": "yes_encrypted",
        "psp_q4": "yes",
        "psp_q9": "yes",
    }
    result = detect_payment_platform_saq(answers)
    assert "ROC" in result["likely_saq"]
    assert result["confidence"] == "high"


def test_scope_service_payment_platform_saq_d():
    """Scope service payment platform returns SAQ D for storing/processing."""
    answers = {"psp_q2": "yes", "psp_q3": "yes_encrypted", "psp_q9": "yes"}
    scope = ScopeService.compute_scope("payment_platform", answers)
    assert scope.likely_saq
    assert "SAQ D" in scope.likely_saq or "ROC" in scope.likely_saq
    assert scope.explanation


def test_scope_service_payment_platform_roc():
    """Scope service payment platform returns ROC for large-scale."""
    answers = {
        "psp_q2": "yes",
        "psp_q3": "yes_encrypted",
        "psp_q4": "yes",
        "psp_q9": "yes",
    }
    scope = ScopeService.compute_scope("payment_platform", answers)
    assert "ROC" in scope.likely_saq


def test_detect_payment_platform_never_claims_compliance():
    """Result text should never claim official compliance."""
    answers = {"psp_q2": "yes", "psp_q3": "yes_encrypted"}
    result = detect_payment_platform_saq(answers)
    full_text = " ".join(
        result.get("explanation", [])
        + result.get("recommendations", [])
        + result.get("next_steps", [])
    ).lower()
    assert "officially compliant" not in full_text
    assert "definitively" not in full_text
