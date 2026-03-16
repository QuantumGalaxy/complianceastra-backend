"""
Phase 9: Admin console tests.

Tests permissions, assessments list, notes, reports, audit.
"""
import pytest
from httpx import AsyncClient

from app.models.assessment import Assessment, AssessmentStatus
from app.models.report import Report
from app.models.user import User
from app.models.admin_note import AdminNote
from app.models.audit_event import AuditEvent
from app.core.auth import get_password_hash, create_access_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


@pytest.fixture
async def completed_assessment(db_session: AsyncSession, test_user):
    """Create completed assessment."""
    scope_result = {
        "summary": "Test",
        "scope_level": "reduced",
        "in_scope": [],
        "out_of_scope": [],
        "risk_areas": [],
        "recommendations": [],
    }
    a = Assessment(
        user_id=test_user.id,
        environment_type="ecommerce",
        status=AssessmentStatus.COMPLETED.value,
        scope_result=scope_result,
    )
    db_session.add(a)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(a)
    return a


# --- Permissions ---
@pytest.mark.asyncio
async def test_admin_assessments_requires_admin(client: AsyncClient):
    """Non-admin cannot access admin assessments."""
    resp = await client.get("/api/admin/assessments")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_assessments_403_for_user(
    client: AsyncClient, auth_headers, completed_assessment
):
    """Regular user gets 403 for admin endpoints."""
    resp = await client.get("/api/admin/assessments", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_assessments_200_for_admin(
    client: AsyncClient, admin_headers, completed_assessment
):
    """Admin can list assessments."""
    resp = await client.get("/api/admin/assessments", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "assessments" in data
    assert len(data["assessments"]) >= 1


# --- Filters ---
@pytest.mark.asyncio
async def test_admin_assessments_filter_scope_level(
    client: AsyncClient, db_session: AsyncSession, admin_headers, test_user
):
    """Filter by scope_level returns only matching assessments."""
    a1 = Assessment(
        user_id=test_user.id,
        environment_type="ecommerce",
        status="completed",
        scope_result={"scope_level": "reduced", "summary": "x", "in_scope": [], "out_of_scope": [], "risk_areas": [], "recommendations": []},
    )
    a2 = Assessment(
        user_id=test_user.id,
        environment_type="ecommerce",
        status="completed",
        scope_result={"scope_level": "expanded", "summary": "y", "in_scope": [], "out_of_scope": [], "risk_areas": [], "recommendations": []},
    )
    db_session.add_all([a1, a2])
    await db_session.flush()
    await db_session.commit()

    resp = await client.get("/api/admin/assessments?scope_level=reduced", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    for a in data["assessments"]:
        assert a["scope_level"] == "reduced"


# --- Notes ---
@pytest.mark.asyncio
async def test_admin_add_note(
    client: AsyncClient, admin_headers, completed_assessment, db_session
):
    """Admin can add note to assessment."""
    resp = await client.post(
        f"/api/admin/assessments/{completed_assessment.id}/notes",
        json={"note": "Internal consultant note"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["note"] == "Internal consultant note"
    assert "id" in data
    assert "created_at" in data

    result = await db_session.execute(
        select(AdminNote).where(AdminNote.assessment_id == completed_assessment.id)
    )
    note = result.scalar_one_or_none()
    assert note is not None
    assert note.note == "Internal consultant note"


@pytest.mark.asyncio
async def test_admin_add_note_403_for_user(
    client: AsyncClient, auth_headers, completed_assessment
):
    """Regular user cannot add note."""
    resp = await client.post(
        f"/api/admin/assessments/{completed_assessment.id}/notes",
        json={"note": "Hack attempt"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


# --- Assessment detail + audit ---
@pytest.mark.asyncio
async def test_admin_get_assessment_detail(
    client: AsyncClient, admin_headers, completed_assessment, db_session
):
    """Admin can get assessment detail with notes."""
    resp = await client.get(
        f"/api/admin/assessments/{completed_assessment.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == completed_assessment.id
    assert "scope_result" in data
    assert "notes" in data

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "assessment",
            AuditEvent.entity_id == completed_assessment.id,
            AuditEvent.action == "admin_viewed",
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None


# --- Organizations ---
@pytest.mark.asyncio
async def test_admin_list_organizations(client: AsyncClient, admin_headers):
    """Admin can list organizations."""
    resp = await client.get("/api/admin/organizations", headers=admin_headers)
    assert resp.status_code == 200
    assert "organizations" in resp.json()


# --- Reports ---
@pytest.mark.asyncio
async def test_admin_list_reports(client: AsyncClient, admin_headers):
    """Admin can list reports."""
    resp = await client.get("/api/admin/reports", headers=admin_headers)
    assert resp.status_code == 200
    assert "reports" in resp.json()


# --- Audit ---
@pytest.mark.asyncio
async def test_admin_list_audit(client: AsyncClient, admin_headers):
    """Admin can list audit events."""
    resp = await client.get("/api/admin/audit", headers=admin_headers)
    assert resp.status_code == 200
    assert "events" in resp.json()


# --- Users with reports_count ---
@pytest.mark.asyncio
async def test_admin_users_includes_reports_count(
    client: AsyncClient, admin_headers, test_user, db_session
):
    """Admin users list includes reports_count."""
    r = Report(user_id=test_user.id, assessment_id=1, status="generated", file_path="x.pdf")
    db_session.add(r)
    await db_session.flush()
    await db_session.commit()

    resp = await client.get("/api/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    for u in data["users"]:
        if u["id"] == test_user.id:
            assert u["reports_count"] >= 1
            break
