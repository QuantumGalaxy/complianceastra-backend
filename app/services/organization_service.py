"""Organization business logic."""
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User
from app.core.exceptions import NotFoundError, ValidationError


def slugify(name: str) -> str:
    """Generate URL-safe slug from name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:100] or "org"


class OrganizationService:
    """Organization CRUD and membership."""

    @staticmethod
    async def get_or_404(db: AsyncSession, org_id: int) -> Organization:
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise NotFoundError("Organization", org_id)
        return org

    @staticmethod
    async def list_for_user(db: AsyncSession, user: User) -> list[Organization]:
        """List organizations the user belongs to (via organization_id)."""
        if not user.organization_id:
            return []
        result = await db.execute(
            select(Organization).where(
                Organization.id == user.organization_id,
                Organization.is_active,
            )
        )
        org = result.scalar_one_or_none()
        return [org] if org else []

    @staticmethod
    async def create(db: AsyncSession, name: str, user: User) -> Organization:
        """Create organization and assign user to it."""
        slug = slugify(name)
        existing = await db.execute(select(Organization).where(Organization.slug == slug))
        if existing.scalar_one_or_none():
            raise ValidationError(f"Organization with slug '{slug}' already exists")
        org = Organization(name=name, slug=slug, is_active=True)
        db.add(org)
        await db.flush()
        user.organization_id = org.id
        await db.flush()
        await db.refresh(org)
        return org

    @staticmethod
    async def update(db: AsyncSession, org: Organization, name: str) -> Organization:
        """Update organization name and slug."""
        org.name = name
        org.slug = slugify(name)
        await db.flush()
        await db.refresh(org)
        return org

    @staticmethod
    def user_can_edit(org: Organization, user: User) -> bool:
        """Check if user can edit org (member of org)."""
        return user.organization_id == org.id
