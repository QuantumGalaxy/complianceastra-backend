"""Transactional email (Resend). Optional — set RESEND_API_KEY in production."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"


async def send_guest_checkout_email(
    to_email: str,
    *,
    setup_token: str,
    dashboard_url: str,
    login_url: str,
    set_password_base_url: str,
    report_path: str | None,
    app_name: str | None = None,
) -> bool:
    """
    After first-time purchase: link to create password, dashboard, login; optional PDF attachment.
    """
    settings = get_settings()
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        logger.warning(
            "RESEND_API_KEY not set; guest checkout email skipped. "
            "Set RESEND_API_KEY so users receive their password setup link."
        )
        return False

    name = app_name or settings.APP_NAME
    from_addr = (settings.MAIL_FROM or "").strip() or f"{name} <onboarding@resend.dev>"

    enc = quote(setup_token, safe="")
    set_password_link = f"{set_password_base_url.rstrip('/')}?token={enc}"

    lines = [
        f"<p>Thanks for your purchase from {name}.</p>",
        "<p><strong>Next step:</strong> create your password to access your dashboard and download your report.</p>",
        f'<p><a href="{set_password_link}" style="display:inline-block;padding:12px 20px;background:#059669;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">Create your password</a></p>',
        f"<p>Or open this link: <br/><span style=\"word-break:break-all;font-size:13px;\">{set_password_link}</span></p>",
        f'<p>Dashboard (after password): <a href="{dashboard_url}">{dashboard_url}</a></p>',
        f'<p>Log in later: <a href="{login_url}">{login_url}</a></p>',
    ]

    html = "\n".join(lines)

    payload: dict = {
        "from": from_addr,
        "to": [to_email],
        "subject": f"Complete your account — {name}",
        "html": html,
    }

    if report_path and Path(report_path).is_file():
        try:
            raw = Path(report_path).read_bytes()
            payload["attachments"] = [
                {
                    "filename": f"pci_readiness_report_{Path(report_path).stem}.pdf",
                    "content": base64.b64encode(raw).decode("ascii"),
                }
            ]
        except OSError as e:
            logger.warning("Could not attach report PDF %s: %s", report_path, e)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(RESEND_API, json=payload, headers=headers)
        if r.status_code >= 400:
            logger.error("Resend API error %s: %s", r.status_code, r.text)
            return False
        logger.info("Guest checkout email queued for %s", to_email[:3] + "***")
        return True
    except Exception:
        logger.exception("Failed to send guest checkout email to %s", to_email[:3] + "***")
        return False


async def send_existing_user_receipt_email(
    to_email: str,
    *,
    dashboard_url: str,
    login_url: str,
    report_path: str | None,
    app_name: str | None = None,
) -> bool:
    """Optional receipt for returning customers (no password setup)."""
    settings = get_settings()
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        return False
    name = app_name or settings.APP_NAME
    from_addr = (settings.MAIL_FROM or "").strip() or f"{name} <onboarding@resend.dev>"
    html = (
        f"<p>Thanks for your purchase from {name}.</p>"
        f'<p><a href="{dashboard_url}">Open your dashboard</a> — '
        f'<a href="{login_url}">Log in</a> with your existing password.</p>'
    )
    payload: dict = {
        "from": from_addr,
        "to": [to_email],
        "subject": f"Your {name} report is ready",
        "html": html,
    }
    if report_path and Path(report_path).is_file():
        try:
            raw = Path(report_path).read_bytes()
            payload["attachments"] = [
                {
                    "filename": f"pci_readiness_report_{Path(report_path).stem}.pdf",
                    "content": base64.b64encode(raw).decode("ascii"),
                }
            ]
        except OSError:
            pass
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(RESEND_API, json=payload, headers=headers)
        return r.status_code < 400
    except Exception:
        logger.exception("Receipt email failed")
        return False


async def send_password_reset_email(
    to_email: str,
    *,
    reset_token: str,
    reset_password_base_url: str,
    app_name: str | None = None,
) -> bool:
    """Forgot-password flow."""
    settings = get_settings()
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        logger.warning("RESEND_API_KEY not set; password reset email skipped")
        return False
    name = app_name or settings.APP_NAME
    from_addr = (settings.MAIL_FROM or "").strip() or f"{name} <onboarding@resend.dev>"
    enc = quote(reset_token, safe="")
    link = f"{reset_password_base_url.rstrip('/')}?token={enc}"
    html = (
        f"<p>You asked to reset your password for {name}.</p>"
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;background:#059669;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">Reset password</a></p>'
        f"<p style=\"word-break:break-all;font-size:13px;\">{link}</p>"
        "<p>If you didn’t request this, you can ignore this email.</p>"
    )
    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": f"Reset your {name} password",
        "html": html,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(RESEND_API, json=payload, headers=headers)
        return r.status_code < 400
    except Exception:
        logger.exception("Password reset email failed")
        return False


async def send_password_setup_reminder_email(
    to_email: str,
    *,
    setup_token: str,
    set_password_base_url: str,
    app_name: str | None = None,
) -> bool:
    """User exists but never finished checkout password — e.g. forgot-password for pending account."""
    settings = get_settings()
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        return False
    name = app_name or settings.APP_NAME
    from_addr = (settings.MAIL_FROM or "").strip() or f"{name} <onboarding@resend.dev>"
    enc = quote(setup_token, safe="")
    link = f"{set_password_base_url.rstrip('/')}?token={enc}"
    html = (
        f"<p>Finish setting up your {name} account to access your reports.</p>"
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;background:#059669;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">Create your password</a></p>'
        f"<p style=\"word-break:break-all;font-size:13px;\">{link}</p>"
    )
    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": f"Complete your {name} account",
        "html": html,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(RESEND_API, json=payload, headers=headers)
        return r.status_code < 400
    except Exception:
        logger.exception("Password setup reminder email failed")
        return False
