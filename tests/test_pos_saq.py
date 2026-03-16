"""
Tests for POS SAQ detection logic.
"""
import pytest

from app.services.pos_saq_logic import detect_pos_saq
from app.services.scope_service import ScopeService


def _base_pos_answers() -> dict:
    """Minimal POS answers that are not 'not sure' for non-critical questions."""
    return {
        "terminal_type": "standalone",
        "locations": "1",
        "pos_q7": "no",
        "pos_q8": "no",
        "pos_q9": "yes",
        "pos_q10": "no",
        "p2pe": "no",
        "pos_q12": "yes",
        "pos_q13": "no",
        "pos_q14": "processor",
        "pos_q15": "yes",
        "network_segmentation": "yes_full",
        "pos_q18": "yes",
        "pos_q19": "no",
        "pos_q31": "no",
        "pos_q32": "yes",
        "pos_q33": "yes",
        "pos_q34": "yes",
    }


def test_strong_p2pe():
    """Test Case 1: Strong P2PE - standalone, validated P2PE, encrypted at terminal, no decryption, no PAN storage."""
    answers = _base_pos_answers()
    answers["terminal_type"] = "standalone"
    answers["p2pe"] = "p2pe_validated"
    answers["pos_q12"] = "yes"
    answers["pos_q13"] = "no"
    answers["pos_q7"] = "no"
    answers["pos_q8"] = "no"
    answers["network_segmentation"] = "yes_full"

    result = detect_pos_saq(answers)
    assert result["likely_saq"] == "P2PE"
    assert result["confidence"] == "high"
    assert "in_scope_items" in result
    assert "out_scope_items" in result


def test_strong_b():
    """Test Case 2: Strong B - standalone, no PAN storage, no decryption, simple environment."""
    answers = _base_pos_answers()
    answers["terminal_type"] = "standalone"
    answers["pos_q7"] = "no"
    answers["pos_q13"] = "no"
    answers["pos_q14"] = "processor"
    answers["p2pe"] = "no"
    answers["network_segmentation"] = "yes_full"

    result = detect_pos_saq(answers)
    assert result["likely_saq"] == "B"
    assert result["confidence"] in ("high", "medium")


def test_strong_d_by_storage():
    """Test Case 3: Strong D - full PAN stored electronically."""
    answers = _base_pos_answers()
    answers["pos_q7"] = "yes"

    result = detect_pos_saq(answers)
    assert result["likely_saq"] == "D"
    assert result["confidence"] in ("high", "medium")


def test_strong_d_by_integrated_processing():
    """Test Case 4: Strong D - integrated POS, direct processing, weak segmentation."""
    answers = _base_pos_answers()
    answers["terminal_type"] = "integrated"
    answers["pos_q14"] = "yes"
    answers["network_segmentation"] = "no_shared"

    result = detect_pos_saq(answers)
    assert result["likely_saq"] == "D"


def test_contradiction():
    """Test Case 5: Contradiction - P2PE yes but decryption in environment yes."""
    answers = _base_pos_answers()
    answers["p2pe"] = "p2pe_validated"
    answers["pos_q13"] = "yes"

    result = detect_pos_saq(answers)
    assert result["likely_saq"] in ("D", "Needs Review")
    assert result["confidence"] in ("low", "medium")
    assert "contradiction" in str(result.get("explanation", [])).lower() or "contradict" in str(result.get("explanation", [])).lower()


def test_too_many_not_sure():
    """Test Case 6: Too many 'not sure' on critical questions."""
    answers = {
        "pos_q7": "not_sure",
        "pos_q8": "not_sure",
        "p2pe": "unsure",
        "pos_q12": "not_sure",
        "pos_q13": "not_sure",
        "network_segmentation": "not_sure",
        "pos_q31": "not_sure",
        "pos_q14": "not_sure",
    }

    result = detect_pos_saq(answers)
    assert result["confidence"] == "low"
    assert result["likely_saq"] in ("D", "Needs Review")
    assert len(result.get("information_gaps", [])) >= 4


def test_scope_service_pos_includes_likely_saq():
    """Scope service POS result includes likely_saq and confidence from pos_saq_logic."""
    answers = {
        "terminal_type": "standalone",
        "pos_q7": "no",
        "pos_q8": "no",
        "p2pe": "p2pe_validated",
        "pos_q12": "yes",
        "pos_q13": "no",
        "network_segmentation": "yes_full",
    }
    scope = ScopeService.compute_scope("pos", answers)
    assert scope.likely_saq == "P2PE"
    assert scope.confidence in ("high", "medium")
    assert scope.explanation
    assert "suggested_saq" in scope.model_dump() or scope.suggested_saq


def test_scope_service_pos_d_by_storage():
    """Scope service returns D when PAN is stored."""
    answers = {"pos_q7": "yes"}
    scope = ScopeService.compute_scope("pos", answers)
    assert scope.likely_saq == "D"
    assert scope.scope_level == "expanded"


def test_detect_pos_saq_never_claims_compliance():
    """Result text should never claim official compliance."""
    answers = _base_pos_answers()
    answers["p2pe"] = "p2pe_validated"
    answers["pos_q12"] = "yes"
    answers["pos_q13"] = "no"
    answers["network_segmentation"] = "yes_full"

    result = detect_pos_saq(answers)
    full_text = " ".join(
        result.get("explanation", [])
        + result.get("recommendations", [])
        + result.get("next_steps", [])
    ).lower()
    assert "officially compliant" not in full_text
    assert "definitively" not in full_text
    assert "certified" not in full_text or "not certified" in full_text
