from __future__ import annotations

import os
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from services.sms_service import load_local_env

email_logger = logging.getLogger("gumus_veteriner.email")


@dataclass(frozen=True)
class EmailResult:
    success: bool
    message: str
    detail: str = ""


def env_flag(name: str, default: bool = False) -> bool:
    """Render Environment içindeki true/false değerlerini güvenli biçimde çözer."""
    fallback = "true" if default else "false"
    return (os.environ.get(name) or fallback).strip().lower() in {"1", "true", "yes", "on"}


def send_email(to_email: str, subject: str, body: str) -> EmailResult:
    """Google App Password ile SMTP üzerinden kullanıcıya işlem maili gönderir."""
    load_local_env()
    recipient = (to_email or "").strip()
    if not recipient:
        return EmailResult(False, "E-posta adresi yok")

    host = (os.environ.get("SMTP_HOST") or "").strip()
    username = (os.environ.get("SMTP_USERNAME") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or username).strip()
    use_tls = env_flag("SMTP_USE_TLS", default=True)
    try:
        port = int((os.environ.get("SMTP_PORT") or "587").strip())
    except ValueError:
        email_logger.error("SMTP_PORT geçerli bir sayı değil")
        return EmailResult(False, "Mail gönderilemedi", "SMTP_PORT geçerli bir sayı değil")

    # Google App Password ekranda dörderli gruplar halinde gösterilebilir.
    # Render'a boşluklu yapıştırılsa bile Gmail için doğru değeri kullanırız.
    if host.lower() == "smtp.gmail.com":
        password = password.replace(" ", "")

    if not host or not sender:
        email_logger.error("SMTP ayarları eksik: SMTP_HOST ve SMTP_FROM zorunludur")
        return EmailResult(False, "Mail gönderilemedi", "SMTP ortam değişkenleri eksik")
    if bool(username) != bool(password):
        email_logger.error("SMTP kimlik bilgileri eksik: kullanıcı adı ve parola birlikte tanımlanmalıdır")
        return EmailResult(False, "Mail gönderilemedi", "SMTP kimlik bilgileri eksik")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # SMTP hatasını API kullanıcısına traceback olarak göstermiyoruz.
        email_logger.exception(
            "SMTP mail gönderimi başarısız: alıcı=%s sunucu=%s port=%s tls=%s hata=%s",
            recipient,
            host,
            port,
            use_tls,
            exc,
        )
        return EmailResult(False, "Mail gönderilemedi", str(exc))
    email_logger.info("SMTP mail gönderildi: alıcı=%s sunucu=%s port=%s tls=%s", recipient, host, port, use_tls)
    return EmailResult(True, "Mail gönderildi")
