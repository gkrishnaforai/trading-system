"""Outbound mail — SMTP only, no vendor SDK.

Env:
  MP_SMTP_HOST / MP_SMTP_PORT(587) / MP_SMTP_USER / MP_SMTP_PASS
  MP_SMTP_FROM   — From: header (defaults to user, then noreply@)
  MP_APP_URL     — public site origin used to build action links
                   (defaults to http://localhost:3000)

With no MP_SMTP_HOST the send is a logged no-op returning False —
signup still lands, the verification link lands in the worker log
(dev loop never dead-ends on missing creds). Any free SMTP tier
(Resend/Brevo ~100+/day, Gmail app-password) covers this volume.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _cfg() -> dict:
    return {
        "host": os.getenv("MP_SMTP_HOST", "").strip(),
        "port": int(os.getenv("MP_SMTP_PORT", "587")),
        "user": os.getenv("MP_SMTP_USER", "").strip(),
        "password": os.getenv("MP_SMTP_PASS", "").strip(),
        "sender": (os.getenv("MP_SMTP_FROM", "").strip()
                   or os.getenv("MP_SMTP_USER", "").strip()
                   or "noreply@osprey-desk.local"),
    }


def app_url() -> str:
    return os.getenv("MP_APP_URL", "http://localhost:3000").rstrip("/")


def send(to: str, subject: str, text: str) -> bool:
    """One plaintext message. Returns False when SMTP is unconfigured
    (link logged) or the send fails — callers decide whether to nag."""
    c = _cfg()
    if not c["host"]:
        logger.info("mailer(no smtp): to=%s subject=%s\n%s",
                    to, subject, text)
        return False
    msg = EmailMessage()
    msg["From"] = c["sender"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    try:
        with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
            s.ehlo()
            s.starttls()
            if c["user"]:
                s.login(c["user"], c["password"])
            s.send_message(msg)
        return True
    except Exception as e:                                  # noqa: BLE001
        logger.warning("mailer send failed to %s: %s", to, e)
        return False


def send_verification(email: str, link: str) -> bool:
    return send(
        email,
        "Verify your email — Osprey Desk",
        "Confirm this address to finish setting up your account:\n\n"
        f"    {link}\n\n"
        "The link expires in 24 hours. If you didn't create this "
        "account, ignore this message.\n",
    )
