"""Assessment and answer models."""
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class EnvironmentType(str, enum.Enum):
    ECOMMERCE = "ecommerce"
    POS = "pos"
    PAYMENT_PLATFORM = "payment_platform"


class AssessmentStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    framework: Mapped[str] = mapped_column(String(50), default="pci_dss")
    environment_type: Mapped[str] = mapped_column(String(50))
    rule_set_id: Mapped[int | None] = mapped_column(ForeignKey("rule_sets.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=AssessmentStatus.IN_PROGRESS.value)
    current_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Computed scope summary
    anonymous_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="assessments")
    answers = relationship("AssessmentAnswer", back_populates="assessment", cascade="all, delete-orphan")


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    answer_value: Mapped[str] = mapped_column(Text)  # JSON string or simple value
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="answers")
