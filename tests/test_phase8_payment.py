"""
Phase 8: Stripe payment flow tests.

Tests checkout, download auth, and webhook handling (mocked).
Uses conftest's test_user and auth_headers where possible.
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient

from app.models.assessment import Assessment, AssessmentStatus
from app.models.report import Report
from app.models.user import User
from app.core.auth import get_password_hash, create_access_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


@pytest.fixture
async def completed_assessment(db_session: AsyncSession, test_user):
    """Create completed assessment owned by test user."""
    user_id = test_user.id
    scope_result = {
        "summary": "Test scope",
        "in_scope": ["A", "B"],
        "out_of_scope": ["C"],
        "risk_areas": [],
        "recommendations": ["Do X"],
        "scope_level": "reduced",
        "suggested_saq": "SAQ A",
        "next_steps": ["Step 1"],
    }
    a = Assessment(
        user_id=user_id,
        environment_type="ecommerce",
        status=AssessmentStatus.COMPLETED.value,
        scope_result=scope_result,
    )
    db_session.add(a)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(a)
    return a


# --- Checkout ---
@pytest.mark.asyncio
async def test_checkout_requires_auth(client: AsyncClient, completed_assessment):
    """Checkout without token returns 401."""
    resp = await client.post(
        "/api/reports/checkout",
        json={"assessment_id": completed_assessment.id},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_checkout_requires_completed_assessment(
    client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
):
    """Checkout for in-progress assessment returns 400."""
    user_id = test_user.id
    a = Assessment(
        user_id=user_id,
        environment_type="ecommerce",
        status="in_progress",
        scope_result=None,
    )
    db_session.add(a)
    await db_session.flush()

    resp = await client.post(
        "/api/reports/checkout",
        json={"assessment_id": a.id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_checkout_requires_ownership(
    client: AsyncClient, db_session: AsyncSession, completed_assessment, auth_headers
):
    """Checkout for assessment owned by another user returns 400."""
    # Create another user
    other = User(
        email="other@example.com",
        hashed_password=get_password_hash("other123"),
        full_name="Other",
        role="user",
    )
    db_session.add(other)
    await db_session.flush()
    token = create_access_token({"sub": other.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/reports/checkout",
        json={"assessment_id": completed_assessment.id},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("app.services.payment_service.PaymentService.is_configured", return_value=False)
async def test_checkout_returns_503_when_stripe_not_configured(
    mock_configured, client: AsyncClient, completed_assessment, auth_headers
):
    """Checkout when Stripe not configured returns 503."""
    resp = await client.post(
        "/api/reports/checkout",
        json={"assessment_id": completed_assessment.id},
        headers=auth_headers,
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
@patch("app.services.payment_service.PaymentService.is_configured", return_value=True)
@patch("stripe.checkout.Session.create")
async def test_checkout_creates_report_and_returns_url(
    mock_create, mock_configured, client: AsyncClient, completed_assessment, auth_headers, test_user, db_session
):
    """Checkout creates Report and returns checkout_url."""
    mock_create.return_value = MagicMock(
        id="cs_test_123",
        url="https://checkout.stripe.com/c/pay/cs_test_123",
    )
    user_id = test_user.id

    resp = await client.post(
        "/api/reports/checkout",
        json={"assessment_id": completed_assessment.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "checkout_url" in data
    assert "session_id" in data
    assert data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_123"
    assert data["session_id"] == "cs_test_123"

    result = await db_session.execute(select(Report).where(Report.stripe_payment_id == "cs_test_123"))
    report = result.scalar_one_or_none()
    assert report is not None
    assert report.user_id == user_id
    assert report.assessment_id == completed_assessment.id
    assert report.status == "pending"


# --- Download ---
@pytest.mark.asyncio
async def test_download_requires_auth(client: AsyncClient):
    """Download without token returns 401."""
    resp = await client.get("/api/reports/1/download")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_download_returns_404_for_nonexistent(client: AsyncClient, auth_headers):
    """Download for non-existent report returns 404."""
    resp = await client.get("/api/reports/99999/download", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_returns_404_when_not_generated(
    client: AsyncClient, db_session: AsyncSession, auth_headers, test_user, completed_assessment
):
    """Download for pending report returns 404."""
    user_id = test_user.id
    r = Report(user_id=user_id, assessment_id=completed_assessment.id, status="pending")
    db_session.add(r)
    await db_session.flush()
    await db_session.refresh(r)

    resp = await client.get(f"/api/reports/{r.id}/download", headers=auth_headers)
    assert resp.status_code == 404


# --- Webhook (mocked) ---
@pytest.mark.asyncio
@patch("app.api.stripe_webhook.settings")
async def test_webhook_returns_503_when_not_configured(mock_settings, client: AsyncClient):
    """Webhook when STRIPE_WEBHOOK_SECRET not set returns 503."""
    mock_settings.STRIPE_WEBHOOK_SECRET = ""
    mock_settings.STRIPE_SECRET_KEY = "sk_test"
    resp = await client.post(
        "/api/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "invalid"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
@patch("app.api.stripe_webhook.settings")
async def test_webhook_returns_400_for_invalid_signature(mock_settings, client: AsyncClient):
    """Webhook with invalid signature returns 400."""
    mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    mock_settings.STRIPE_SECRET_KEY = "sk_test"
    resp = await client.post(
        "/api/webhooks/stripe",
        content=b'{"type":"checkout.session.completed"}',
        headers={"stripe-signature": "invalid"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("stripe.Webhook.construct_event")
async def test_webhook_idempotent_when_report_not_found(
    mock_construct, client: AsyncClient, db_session: AsyncSession
):
    """Webhook returns 200 when Report not found (idempotent)."""
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_unknown",
                "metadata": {"assessment_id": "1", "user_id": "1"},
            }
        },
    }
    # Patch settings to have webhook secret
    with patch("app.api.stripe_webhook.settings") as mock_settings:
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        mock_settings.STRIPE_SECRET_KEY = "sk_test"
        resp = await client.post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=abc"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
