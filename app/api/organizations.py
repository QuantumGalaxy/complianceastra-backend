"""Organization endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user_required
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationUpdate, OrganizationResponse
from app.services.organization_service import OrganizationService
from app.core.exceptions import ForbiddenError

router = APIRouter()


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """List organizations the current user belongs to."""
    orgs = await OrganizationService.list_for_user(db, current_user)
    return [OrganizationResponse.model_validate(o) for o in orgs]


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Get organization by ID. User must be a member."""
    org = await OrganizationService.get_or_404(db, org_id)
    if not OrganizationService.user_can_edit(org, current_user):
        raise ForbiddenError("Not a member of this organization")
    return OrganizationResponse.model_validate(org)


@router.post("", status_code=201, response_model=OrganizationResponse)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Create organization and assign current user to it."""
    org = await OrganizationService.create(db, data.name, current_user)
    return OrganizationResponse.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Update organization. User must be a member."""
    org = await OrganizationService.get_or_404(db, org_id)
    if not OrganizationService.user_can_edit(org, current_user):
        raise ForbiddenError("Not a member of this organization")
    org = await OrganizationService.update(db, org, data.name)
    return OrganizationResponse.model_validate(org)
