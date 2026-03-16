"""Question and rule models for data-driven assessments."""
from sqlalchemy import String, Integer, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_set_version: Mapped[int] = mapped_column(Integer, default=1)
    environment_type: Mapped[str] = mapped_column(String(50))  # ecommerce, pos, payment_platform
    question_key: Mapped[str] = mapped_column(String(100), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20))  # single_choice, multi_choice, text, yes_no
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(50))  # transaction_flow, controls, etc.
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_question_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Branching logic

    options = relationship("QuestionOption", back_populates="question")
    rules = relationship("QuestionRule", back_populates="question")


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    option_value: Mapped[str] = mapped_column(String(100))
    option_label: Mapped[str] = mapped_column(String(255))
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    question = relationship("Question", back_populates="options")


class QuestionRule(Base):
    """Rules for scope computation based on answers."""
    __tablename__ = "question_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    condition: Mapped[dict] = mapped_column(JSON)  # e.g. {"answer": "yes", "scope_impact": "increase"}
    scope_impact: Mapped[str] = mapped_column(String(50))
    message_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    question = relationship("Question", back_populates="rules")
