"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.auth import verify_password, get_password_hash, create_access_token, get_current_user_required
from app.core.password_setup import PWD_SETUP_TYP
from app.models.report import Report
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    PostCheckoutRequest,
    PostCheckoutResponse,
    SetPasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
)
from app.services.password_reset_service import consume_password_reset_token, create_password_reset_token
from app.services.email_service import send_password_reset_email, send_password_setup_reminder_email

router = APIRouter()
settings = get_settings()


@router.post("/register", response_model=Token)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        password_ready=True,
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
    if not user.password_ready:
        raise HTTPException(
            status_code=403,
            detail="Complete password setup using the link from your purchase email, or use Forgot password.",
        )
    token = create_access_token({"sub": str(user.id)})
    return Token(
        access_token=token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active),
    )


@router.post("/post-checkout", response_model=PostCheckoutResponse)
async def post_checkout(data: PostCheckoutRequest, db: AsyncSession = Depends(get_db)):
    """
    After Stripe redirects with ?session_id= — exchange for login JWT or a password-setup token.
    """
    from app.services.checkout_completion import fulfill_paid_checkout_session

    sid = data.session_id.strip()
    if sid == "dev_bypass" and settings.STRIPE_DEV_BYPASS:
        raise HTTPException(
            status_code=400,
            detail="Dev bypass is completed in the app after payment. Use the redirect from checkout, or log in.",
        )

    out = await fulfill_paid_checkout_session(db, sid)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "checkout_failed"))
    result = await db.execute(select(User).where(User.id == out["user_id"]))
    user = result.scalar_one()
    return PostCheckoutResponse(
        access_token=out.get("access_token"),
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
        ),
        needs_password_setup=bool(out.get("needs_password_setup")),
        setup_token=out.get("setup_token"),
    )


@router.post("/complete-password", response_model=Token)
async def complete_password(data: SetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    One endpoint for (1) first-time checkout JWT in `token`, or (2) forgot-password raw token.
    """
    raw = data.token.strip()
    pwd = data.password

    payload: dict | None = None
    try:
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        payload = None

    if payload and payload.get("typ") == PWD_SETUP_TYP:
        user_id = int(payload["sub"])
        sid = payload.get("sid")
        if not sid:
            raise HTTPException(status_code=400, detail="Invalid token")
        u_result = await db.execute(select(User).where(User.id == user_id))
        user = u_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=400, detail="Invalid token")
        if user.password_ready:
            raise HTTPException(status_code=400, detail="Password already set. Log in with your email.")
        r = await db.execute(select(Report).where(Report.user_id == user_id, Report.stripe_payment_id == sid))
        report = r.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=400, detail="Invalid or expired checkout link")
        user.hashed_password = get_password_hash(pwd)
        user.password_ready = True
        await db.flush()
        token = create_access_token({"sub": str(user.id)})
        return Token(
            access_token=token,
            user=UserResponse(
                id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active
            ),
        )

    if payload:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Forgot-password raw token
    user = await consume_password_reset_token(db, raw)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    if not user.password_ready:
        user.password_ready = True
    user.hashed_password = get_password_hash(pwd)
    await db.flush()
    token = create_access_token({"sub": str(user.id)})
    return Token(
        access_token=token,
        user=UserResponse(
            id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active
        ),
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Always returns ok=true. Sends reset or setup link when applicable."""
    email = str(data.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    base = settings.FRONTEND_URL.rstrip("/")
    reset_base = f"{base}/auth/reset-password"
    set_pw_base = f"{base}/auth/set-password"

    if user and not user.password_ready:
        r = await db.execute(
            select(Report)
            .where(Report.user_id == user.id, Report.status == "generated")
            .order_by(Report.id.desc())
            .limit(1)
        )
        report = r.scalar_one_or_none()
        if report and report.stripe_payment_id:
            from app.core.password_setup import create_password_setup_token

            setup_tok = create_password_setup_token(user.id, report.stripe_payment_id)
            await send_password_setup_reminder_email(
                user.email,
                setup_token=setup_tok,
                set_password_base_url=set_pw_base,
            )
        return MessageResponse(ok=True)

    if user and user.password_ready:
        raw = await create_password_reset_token(db, user)
        await send_password_reset_email(
            user.email,
            reset_token=raw,
            reset_password_base_url=reset_base,
        )

    return MessageResponse(ok=True)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user_required)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )
