"""
Tests for E-commerce SAQ detection logic.
"""
import pytest

from app.services.ecommerce_saq_logic import detect_ecommerce_saq
from app.services.scope_service import ScopeService


def test_case1_redirect_stripe_no_storage():
    """Case 1: Redirect to Stripe hosted checkout, no card storage -> SAQ A, confidence high."""
    answers = {
        "ecom_q4": "redirect",
        "ecom_q5": "no",
        "ecom_q6": "no",
        "ecom_q7": "no",
        "ecom_q8": "no",
        "ecom_q10": "yes",
    }
    result = detect_ecommerce_saq(answers)
    assert result["likely_saq"] == "A"
    assert result["confidence"] == "high"


def test_case2_stripe_elements_embedded():
    """Case 2: Stripe Elements embedded, no card storage -> SAQ A-EP."""
    answers = {
        "ecom_q4": "embedded",
        "ecom_q5": "no",
        "ecom_q6": "no",
        "ecom_q7": "no",
        "ecom_q8": "no",
    }
    result = detect_ecommerce_saq(answers)
    assert result["likely_saq"] == "A-EP"
    assert result["confidence"] in ("high", "medium")


def test_case3_custom_form_server_receives():
    """Case 3: Custom payment form, server receives card data -> SAQ D."""
    answers = {
        "ecom_q4": "merchant_hosted",
        "ecom_q5": "yes",
        "ecom_q6": "yes",
    }
    result = detect_ecommerce_saq(answers)
    assert result["likely_saq"] == "D"


def test_scope_service_ecommerce_saq_a():
    """Scope service ecommerce returns SAQ A for redirect pattern."""
    answers = {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"}
    scope = ScopeService.compute_scope("ecommerce", answers)
    assert scope.likely_saq == "A"
    assert scope.confidence in ("high", "medium")
    assert scope.explanation


def test_scope_service_ecommerce_saq_a_ep():
    """Scope service ecommerce returns SAQ A-EP for embedded/iframe."""
    answers = {"ecom_q4": "iframe", "ecom_q5": "no", "ecom_q7": "no"}
    scope = ScopeService.compute_scope("ecommerce", answers)
    assert scope.likely_saq == "A-EP"


def test_scope_service_ecommerce_saq_d_by_storage():
    """Scope service ecommerce returns SAQ D when PAN stored."""
    answers = {"ecom_q7": "yes"}
    scope = ScopeService.compute_scope("ecommerce", answers)
    assert scope.likely_saq == "D"
    assert scope.scope_level == "expanded"


def test_detect_ecommerce_saq_never_claims_compliance():
    """Result text should never claim official compliance."""
    answers = {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"}
    result = detect_ecommerce_saq(answers)
    full_text = " ".join(
        result.get("explanation", [])
        + result.get("recommendations", [])
        + result.get("next_steps", [])
    ).lower()
    assert "officially compliant" not in full_text
    assert "definitively" not in full_text
