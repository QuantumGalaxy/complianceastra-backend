"""Admin endpoints - assessments, users, organizations, notes, reports, audit."""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user_required
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.models.lead import ConsultingLead
from app.models.assessment import Assessment
from app.models.organization import Organization
from app.models.report import Report
from app.models.admin_note import AdminNote
from app.models.audit_event import AuditEvent
from app.schemas.admin import AdminNoteCreate
from app.services.audit_service import AuditService

router = APIRouter()


def require_admin(current_user: User = Depends(get_current_user_required)) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


# --- Assessments ---
@router.get("/assessments")
async def list_assessments(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
    scope_level: str | None = Query(None, description="Filter: reduced, standard, expanded"),
    environment_type: str | None = Query(None, description="Filter: ecommerce, pos, payment_platform"),
):
    """List assessments with optional filters. scope_level from scope_result JSON."""
    q = select(Assessment).order_by(Assessment.created_at.desc())
    result = await db.execute(q)
    assessments = result.scalars().all()

    items = []
    for a in assessments:
        scope_level_val = None
        if a.scope_result and isinstance(a.scope_result, dict):
            scope_level_val = a.scope_result.get("scope_level")
        if scope_level and scope_level_val != scope_level:
            continue
        if environment_type and a.environment_type != environment_type:
            continue

        notes_count = await db.execute(
            select(func.count()).select_from(AdminNote).where(AdminNote.assessment_id == a.id)
        )
        notes_count_val = notes_count.scalar() or 0

        items.append({
            "id": a.id,
            "user_id": a.user_id,
            "user_email": None,
            "environment_type": a.environment_type,
            "scope_level": scope_level_val,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
            "notes_count": notes_count_val,
        })

    for item in items:
        if item["user_id"]:
            u = await db.get(User, item["user_id"])
            if u:
                item["user_email"] = u.email

    return {"assessments": items}


@router.get("/assessments/{assessment_id}")
async def get_assessment_detail(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Get assessment detail with scope_result and admin notes."""
    a = await db.get(Assessment, assessment_id)
    if not a:
        raise NotFoundError("Assessment", assessment_id)

    notes_result = await db.execute(
        select(AdminNote).where(AdminNote.assessment_id == assessment_id).order_by(AdminNote.created_at.desc())
    )
    notes = notes_result.scalars().all()

    user_email = None
    if a.user_id:
        u = await db.get(User, a.user_id)
        if u:
            user_email = u.email

    await AuditService.log(
        db, "assessment", assessment_id, "admin_viewed",
        actor_user_id=admin.id, payload={"assessment_id": assessment_id}
    )

    return {
        "id": a.id,
        "user_id": a.user_id,
        "user_email": user_email,
        "environment_type": a.environment_type,
        "status": a.status,
        "scope_result": a.scope_result,
        "created_at": a.created_at.isoformat(),
        "notes": [
            {
                "id": n.id,
                "note": n.note,
                "created_by_user_id": n.created_by_user_id,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ],
    }


@router.post("/assessments/{assessment_id}/notes", status_code=201)
async def add_assessment_note(
    assessment_id: int,
    data: AdminNoteCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Add consultant note to assessment."""
    a = await db.get(Assessment, assessment_id)
    if not a:
        raise NotFoundError("Assessment", assessment_id)

    note = AdminNote(
        assessment_id=assessment_id,
        created_by_user_id=admin.id,
        note=data.note,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)

    await AuditService.log(
        db, "admin_note", note.id, "created",
        actor_user_id=admin.id, payload={"assessment_id": assessment_id, "note_id": note.id}
    )

    return {
        "id": note.id,
        "note": note.note,
        "created_by_user_id": note.created_by_user_id,
        "created_at": note.created_at.isoformat(),
    }


# --- Organizations ---
@router.get("/organizations")
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all organizations (admin only)."""
    result = await db.execute(select(Organization).order_by(Organization.name))
    orgs = result.scalars().all()
    return {
        "organizations": [
            {
                "id": o.id,
                "name": o.name,
                "slug": o.slug,
                "is_active": o.is_active,
                "created_at": o.created_at.isoformat(),
            }
            for o in orgs
        ]
    }


# --- Reports / Paid Customers ---
@router.get("/reports")
async def list_reports(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all reports (paid customers)."""
    result = await db.execute(select(Report).order_by(Report.created_at.desc()))
    reports = result.scalars().all()

    items = []
    for r in reports:
        u = await db.get(User, r.user_id)
        items.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_email": u.email if u else None,
            "assessment_id": r.assessment_id,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        })
    return {"reports": items}


@router.get("/reports/{report_id}/download")
async def download_report_admin(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin download of any report."""
    r = await db.get(Report, report_id)
    if not r:
        raise NotFoundError("Report", report_id)
    if not r.file_path or not os.path.exists(r.file_path):
        raise HTTPException(404, "Report file not found")

    await AuditService.log(
        db, "report", report_id, "admin_downloaded",
        actor_user_id=admin.id, payload={"report_id": report_id, "assessment_id": r.assessment_id}
    )

    return FileResponse(r.file_path, filename="compliance-readiness-report.pdf")


# --- Audit ---
@router.get("/audit")
async def list_audit(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
):
    """List recent audit events."""
    result = await db.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "action": e.action,
                "actor_user_id": e.actor_user_id,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    }


# --- Existing ---
@router.get("/leads")
async def list_leads(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(ConsultingLead).order_by(ConsultingLead.created_at.desc()))
    leads = result.scalars().all()
    return {
        "leads": [
            {
                "id": l.id,
                "email": l.email,
                "name": l.name,
                "environment_type": l.environment_type,
                "assessment_id": l.assessment_id,
                "status": l.status,
                "created_at": l.created_at.isoformat(),
            }
            for l in leads
        ]
    }


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    items = []
    for u in users:
        reports_count = await db.execute(select(func.count()).select_from(Report).where(Report.user_id == u.id))
        items.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "created_at": u.created_at.isoformat(),
            "reports_count": reports_count.scalar() or 0,
        })
    return {"users": items}
