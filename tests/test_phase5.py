"""
Phase 5 API tests: claim, organizations, scope service, checkout.
"""
import pytest
from httpx import AsyncClient

from app.services.scope_service import ScopeService
from app.schemas.assessment import ScopeResult


# --- Scope Service (unit) ---
def test_scope_service_ecommerce_reduced():
    """Ecommerce with redirect + no card data = reduced scope (SAQ A)."""
    answers = {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"}
    scope = ScopeService.compute_scope("ecommerce", answers)
    assert scope.scope_level == "reduced"
    assert scope.likely_saq == "A"
    assert len(scope.recommendations) >= 1


def test_scope_service_ecommerce_expanded():
    """Ecommerce with card storage = expanded scope (SAQ D)."""
    scope = ScopeService.compute_scope("ecommerce", {"ecom_q7": "yes"})
    assert scope.scope_level == "expanded"
    assert scope.likely_saq == "D"
    assert "stor" in scope.summary.lower()  # stores, storage, storing


def test_scope_service_pos_segmentation():
    """POS with P2PE + segmentation = reduced."""
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
    assert scope.scope_level == "reduced"
    assert scope.likely_saq == "P2PE"


def test_scope_service_pos_no_segmentation():
    """POS with PAN storage = expanded (D)."""
    answers = {"pos_q7": "yes", "network_segmentation": "no_shared"}
    scope = ScopeService.compute_scope("pos", answers)
    assert scope.scope_level == "expanded"
    assert scope.likely_saq == "D"




# --- Phase 6: Full engine output ---
def test_scope_service_phase6_output_has_confidence():
    """Phase 6: Output includes confidence_score."""
    scope = ScopeService.compute_scope("ecommerce", {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"})
    assert scope.confidence_score is not None
    assert 0 <= scope.confidence_score <= 100


def test_scope_service_phase6_output_has_classification():
    """Phase 6: Output includes environment_classification."""
    scope = ScopeService.compute_scope("ecommerce", {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"})
    assert scope.environment_classification == "redirect_only_checkout"


def test_scope_service_phase6_output_has_suggested_saq():
    """Phase 6: Output includes suggested_saq."""
    scope = ScopeService.compute_scope("ecommerce", {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"})
    assert scope.suggested_saq == "SAQ A"


def test_scope_service_phase6_output_has_next_steps():
    """Phase 6: Output includes next_steps."""
    scope = ScopeService.compute_scope("ecommerce", {"ecom_q4": "redirect", "ecom_q5": "no", "ecom_q10": "yes"})
    assert scope.next_steps is not None
    assert len(scope.next_steps) >= 1


def test_scope_service_phase6_question_count():
    """Phase 6: Question counts per track (ecommerce: 35, pos: 35, payment_platform: 30)."""
    from app.api.assessments import QUESTIONS_BY_ENV
    expected = {"ecommerce": 35, "pos": 35, "payment_platform": 30}
    for env, questions in QUESTIONS_BY_ENV.items():
        assert len(questions) == expected.get(env, 30), f"{env} should have {expected.get(env, 30)} questions, got {len(questions)}"


# --- Assessment claim (integration) ---
@pytest.mark.asyncio
async def test_claim_anonymous_assessment(client: AsyncClient, auth_headers: dict):
    """Claim flow: create anonymous assessment, register, claim."""
    create_resp = await client.post("/api/assessments", json={"environment_type": "ecommerce"})
    assert create_resp.status_code == 201
    data = create_resp.json()
    aid = data["id"]
    anonymous_id = data.get("anonymous_id")
    assert anonymous_id, "Anonymous assessment should return anonymous_id"

    claim_resp = await client.post(
        "/api/assessments/claim",
        json={"assessment_id": aid, "token": anonymous_id},
        headers=auth_headers,
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["assessment_id"] == aid
    assert claim_resp.json()["ok"] is True

    get_resp = await client.get(f"/api/assessments/{aid}")
    assert get_resp.status_code == 200
    # After claim, assessment is owned by user - we can't easily verify without user context
    # but the claim should succeed


@pytest.mark.asyncio
async def test_claim_requires_auth(client: AsyncClient):
    """Claim without token returns 401."""
    create_resp = await client.post("/api/assessments", json={"environment_type": "ecommerce"})
    aid = create_resp.json()["id"]
    anonymous_id = create_resp.json().get("anonymous_id", "")

    claim_resp = await client.post(
        "/api/assessments/claim",
        json={"assessment_id": aid, "token": anonymous_id},
    )
    assert claim_resp.status_code == 401


@pytest.mark.asyncio
async def test_create_assessment_returns_anonymous_id_when_anonymous(client: AsyncClient):
    """Anonymous assessment creation returns anonymous_id."""
    resp = await client.post("/api/assessments", json={"environment_type": "pos"})
    assert resp.status_code == 201
    assert "anonymous_id" in resp.json()


@pytest.mark.asyncio
async def test_create_assessment_authenticated_no_anonymous_id(client: AsyncClient, auth_headers: dict):
    """Authenticated assessment creation does not return anonymous_id."""
    resp = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert "anonymous_id" not in resp.json()
