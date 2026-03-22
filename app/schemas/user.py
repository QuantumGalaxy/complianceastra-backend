from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_active: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PostCheckoutResponse(BaseModel):
    """After Stripe redirect: JWT when the account can log in; otherwise setup_token for /auth/set-password."""

    access_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse
    needs_password_setup: bool = False
    setup_token: str | None = None


class PostCheckoutRequest(BaseModel):
    """Exchange Stripe Checkout session id for JWT after payment redirect."""

    session_id: str = Field(..., min_length=5, description="Stripe Checkout Session id (cs_...)")


class SetPasswordRequest(BaseModel):
    """Checkout JWT (eyJ...) or forgot-password raw token."""

    token: str = Field(..., min_length=8)
    password: str = Field(..., min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    ok: bool = True
