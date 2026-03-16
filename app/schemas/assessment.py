from pydantic import BaseModel, Field
from typing import Literal

EnvironmentType = Literal["ecommerce", "pos", "payment_platform"]
ConfidenceLevel = Literal["high", "medium", "low"]


class AssessmentCreate(BaseModel):
    environment_type: EnvironmentType


class QuestionOptionSchema(BaseModel):
    value: str
    label: str


class QuestionSchema(BaseModel):
    id: int
    question_key: str
    question_text: str
    question_type: str
    category: str
    help_text: str | None
    options: list[QuestionOptionSchema] | None = None


class AnswerSubmit(BaseModel):
    question_id: int
    answer_value: str


class RecommendationDetail(BaseModel):
    priority: int
    action: str
    rationale: str | None = None
    category: str | None = None


class ScopeResult(BaseModel):
    """Phase 6: Full assessment engine output."""
    summary: str
    in_scope: list[str]
    out_of_scope: list[str]
    risk_areas: list[str]  # Human-readable risk labels for display
    recommendations: list[str]  # Action strings for backward compat
    scope_level: str  # reduced, standard, expanded
    # Phase 6 extensions
    environment_classification: str | None = None
    confidence_score: int | None = None  # 0-100
    risk_flags: list[str] = []  # Internal keys: card_data_storage, etc.
    scope_insights: list[str] = []
    recommendation_details: list[RecommendationDetail] = []
    suggested_saq: str | None = None
    next_steps: list[str] = []
    # POS SAQ detection (Phase 6+)
    likely_saq: str | None = None  # B, P2PE, D, Needs Review
    confidence: ConfidenceLevel | None = None  # high, medium, low
    explanation: list[str] = []
    information_gaps: list[str] = []
