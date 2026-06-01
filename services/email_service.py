from __future__ import annotations

import os
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import requests

from services.sms_service import load_local_env

email_logger = logging.getLogger("gumus_veteriner.email")
BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class EmailResult:
    success: bool
    message: str
    detail: str = ""


def env_flag(name: str, default: bool = False) -> bool:
    """Render Environment içindeki true/false değerlerini güvenli biçimde çözer."""
    fallback = "true" if default else "false"
    return (os.environ.get(name) or fallback).strip().lower() in {"1", "true", "yes", "on"}


def send_brevo_email(recipient: str, subject: str, body: str) -> EmailResult:
    """Render Free ile uyumlu HTTPS Brevo Transactional Email API gönderimi."""
    api_key = (os.environ.get("BREVO_API_KEY") or "").strip()
    sender_email = (
        os.environ.get("BREVO_SENDER_EMAIL")
        or os.environ.get("SMTP_FROM")
        or ""
    ).strip()
    sender_name = (os.environ.get("BREVO_SENDER_NAME") or "Gümüş Veteriner").strip()
    reply_to = (os.environ.get("BREVO_REPLY_TO") or sender_email).strip()
    if not api_key or not sender_email:
        email_logger.error("Brevo ayarları eksik: BREVO_API_KEY ve BREVO_SENDER_EMAIL zorunludur")
        return EmailResult(False, "Mail gönderilemedi", "Brevo ortam değişkenleri eksik")

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    try:
        response = requests.post(
            BREVO_TRANSACTIONAL_EMAIL_URL,
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if response.status_code != 201:
            detail = f"HTTP {response.status_code}: {response.text[:500]}"
            email_logger.error("Brevo mail gönderimi başarısız: alıcı=%s hata=%s", recipient, detail)
            return EmailResult(False, "Mail gönderilemedi", detail)
    except requests.RequestException as exc:
        email_logger.exception("Brevo bağlantısı başarısız: alıcı=%s hata=%s", recipient, exc)
        return EmailResult(False, "Mail gönderilemedi", str(exc))

    email_logger.info("Brevo mail gönderildi: alıcı=%s message_id=%s", recipient, response.json().get("messageId", ""))
    return EmailResult(True, "Mail gönderildi")


def send_smtp_email(recipient: str, subject: str, body: str) -> EmailResult:
    """Ücretli sunucular veya yerel geliştirme için klasik SMTP gönderimi."""
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


def send_email(to_email: str, subject: str, body: str) -> EmailResult:
    """Seçilen sağlayıcı üzerinden kullanıcıya işlem maili gönderir."""
    load_local_env()
    recipient = (to_email or "").strip()
    if not recipient:
        return EmailResult(False, "E-posta adresi yok")

    provider = (os.environ.get("MAIL_PROVIDER") or "smtp").strip().lower()
    if provider == "brevo":
        return send_brevo_email(recipient, subject, body)
    if provider == "smtp":
        return send_smtp_email(recipient, subject, body)
    email_logger.error("Desteklenmeyen MAIL_PROVIDER değeri: %s", provider)
    return EmailResult(False, "Mail gönderilemedi", f"Desteklenmeyen MAIL_PROVIDER: {provider}")
