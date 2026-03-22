"""SAQ wizard assessment sync (guest / pre-checkout)."""
from pydantic import BaseModel, Field, EmailStr


class SaqAssessmentSync(BaseModel):
    """Upsert assessment by browser session id (anonymous_id)."""

    client_session_id: str = Field(..., min_length=4, max_length=64)
    guest_email: str | None = Field(None, max_length=255)
    environment_type: str = Field(..., max_length=50)
    scope_result: dict = Field(default_factory=dict)


class SaqAssessmentSyncResponse(BaseModel):
    assessment_id: int


class GuestCheckoutRequest(BaseModel):
    assessment_id: int = Field(..., gt=0)
    client_session_id: str = Field(..., min_length=4, max_length=64)
    email: EmailStr


class GuestCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    """JWT returned only when STRIPE_DEV_BYPASS simulates payment (local dev)."""
    access_token: str | None = None
    needs_password_setup: bool = False
    setup_token: str | None = None


