"""
Application configuration - uses environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ComplianceAstra"
    DEBUG: bool = False

    # Database - SQLite for dev, postgresql+asyncpg for prod
    DATABASE_URL: str = "sqlite+aiosqlite:///./complianceastra.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID_REPORT: str = ""
    STRIPE_DEV_BYPASS: bool = False  # When True and Stripe not configured, skip to success (dev only)
    FRONTEND_URL: str = "http://localhost:3000"
    REPORTS_DIR: str = "reports"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
