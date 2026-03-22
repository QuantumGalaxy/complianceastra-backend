"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import verify_password, get_password_hash, create_access_token, get_current_user_required
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token, PostCheckoutRequest

router = APIRouter()


@router.post("/register", response_model=Token)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return Token(
        access_token=token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active),
    )


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")
    token = create_access_token({"sub": str(user.id)})
    return Token(
        access_token=token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active),
    )


@router.post("/post-checkout", response_model=Token)
async def post_checkout(data: PostCheckoutRequest, db: AsyncSession = Depends(get_db)):
    """
    After Stripe redirects to the app with ?session_id=cs_..., call this to log in.
    Idempotent with Stripe webhook (user + report are created if not already).
    """
    from app.services.checkout_completion import fulfill_paid_checkout_session

    out = await fulfill_paid_checkout_session(db, data.session_id.strip())
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "checkout_failed"))
    result = await db.execute(select(User).where(User.id == out["user_id"]))
    user = result.scalar_one()
    return Token(
        access_token=out["access_token"],
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user_required)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )
