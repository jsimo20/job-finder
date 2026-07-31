"""Send the digest by email from the local machine.

Credentials come from the environment (.env, loaded by the CLI):
GMAIL_USER is both the SMTP login and the recipient; GMAIL_APP_PASSWORD is a
16-character app password (myaccount.google.com/apppasswords, requires 2FA).
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


def send_digest(body_md: str, date: str) -> None:
    """Send the digest markdown. Raises RuntimeError with a plain message when
    credentials are missing — callers surface it after the digest is already
    written and archived, so a failed send never loses the digest."""
    user = (os.environ.get("GMAIL_USER") or "").strip()
    password = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError(
            "GMAIL_USER / GMAIL_APP_PASSWORD not set — add them to .env "
            "(SETUP.md §6) or run without --email")

    msg = MIMEText(body_md, "plain", "utf-8")
    msg["Subject"] = f"Job Digest — {date}"
    msg["From"] = f"job-finder <{user}>"
    msg["To"] = user

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(user, password)
        server.send_message(msg)
