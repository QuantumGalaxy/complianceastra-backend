"""User endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import get_current_user_required
from app.models.user import User
from app.models.assessment import Assessment
from app.models.report import Report
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user_required)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Update current user profile."""
    if data.full_name is not None:
        current_user.full_name = data.full_name
    await db.flush()
    await db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )


@router.get("/me/assessments")
async def my_assessments(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(Assessment).where(Assessment.user_id == current_user.id).order_by(Assessment.created_at.desc())
    )
    assessments = result.scalars().all()
    return {
        "assessments": [
            {
                "id": a.id,
                "environment_type": a.environment_type,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in assessments
        ]
    }


@router.get("/me/reports")
async def my_reports(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(Report).where(Report.user_id == current_user.id).order_by(Report.created_at.desc()))
    reports = result.scalars().all()
    return {
        "reports": [
            {
                "id": r.id,
                "assessment_id": r.assessment_id,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ]
    }
