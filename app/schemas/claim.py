"""Assessment claim schemas."""
from pydantic import BaseModel, Field


class AssessmentClaimRequest(BaseModel):
    assessment_id: int
    token: str = Field(..., min_length=1)


class AssessmentClaimResponse(BaseModel):
    ok: bool = True
    assessment_id: int
