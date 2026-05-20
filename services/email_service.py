from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from services.sms_service import load_local_env


@dataclass(frozen=True)
class EmailResult:
    success: bool
    message: str
    detail: str = ""


def send_email(to_email: str, subject: str, body: str) -> EmailResult:
    """SMTP ayarlari varsa kullaniciya mail gonderir."""
    load_local_env()
    recipient = (to_email or "").strip()
    if not recipient:
        return EmailResult(False, "E-posta adresi yok")

    host = (os.environ.get("SMTP_HOST") or "").strip()
    port = int(os.environ.get("SMTP_PORT") or "587")
    username = (os.environ.get("SMTP_USERNAME") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or username).strip()
    use_tls = (os.environ.get("SMTP_USE_TLS") or "true").strip().lower() != "false"
    if not host or not sender:
        return EmailResult(False, "SMTP ortam degiskenleri eksik")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # SMTP hatasini API kullanicisina traceback olarak gostermiyoruz.
        return EmailResult(False, "Mail gonderilemedi", str(exc))
    return EmailResult(True, "Mail gonderildi")
