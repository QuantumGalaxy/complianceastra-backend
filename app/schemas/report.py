"""Report and checkout schemas."""
from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    assessment_id: int = Field(..., gt=0)


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
