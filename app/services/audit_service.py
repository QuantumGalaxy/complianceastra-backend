"""Audit logging service for admin and key actions."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditService:
    """Append-only audit logging."""

    @staticmethod
    async def log(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        action: str,
        actor_user_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        """Record an audit event."""
        event = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        db.add(event)
        await db.flush()
