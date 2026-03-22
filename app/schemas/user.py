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


class PostCheckoutRequest(BaseModel):
    """Exchange Stripe Checkout session id for JWT after payment redirect."""

    session_id: str = Field(..., min_length=5, description="Stripe Checkout Session id (cs_...)")
