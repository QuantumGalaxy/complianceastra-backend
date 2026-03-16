"""
ComplianceAstra API - Main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, assessments, reports, users, admin, organizations, stripe_webhook
from app.core.config import get_settings
from app.core.exceptions import AppException

app = FastAPI(
    title="ComplianceAstra API",
    description="PCI DSS scoping and readiness assessment API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(assessments.router, prefix="/api/assessments", tags=["assessments"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(stripe_webhook.router, prefix="/api/webhooks/stripe", tags=["webhooks"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
