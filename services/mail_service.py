from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage

from services.sms_service import load_local_env


mail_logger = logging.getLogger("gumus_veteriner.mail")


@dataclass(frozen=True)
class EmailResult:
    success: bool
    message: str
    detail: str = ""


def env_flag(name: str, default: bool = False) -> bool:
    """Ortam değişkenlerindeki true/false değerlerini güvenli biçimde çözer."""
    fallback = "true" if default else "false"
    return (os.environ.get(name) or fallback).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_mail_provider() -> str:
    """Gmail SMTP'yi varsayılan production mail sağlayıcısı olarak döndürür."""
    return "smtp"


def mail_is_configured() -> bool:
    """Secret değerleri göstermeden SMTP yapılandırmasının varlığını kontrol eder."""
    load_local_env()
    username = (os.environ.get("SMTP_USERNAME") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or username).strip()
    return bool(username and password and sender)


def get_mail_status() -> dict:
    """Secret göstermeden canlı SMTP ayarlarının teşhis bilgisini döndürür."""
    load_local_env()
    host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip().lower()
    username = (os.environ.get("SMTP_USERNAME") or "").strip().lower()
    password = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "").strip()
    configured_sender = (os.environ.get("SMTP_FROM") or username).strip().lower()
    effective_sender = username if host == "smtp.gmail.com" else configured_sender
    try:
        port = int((os.environ.get("SMTP_PORT") or "587").strip())
    except ValueError:
        port = 0
    return {
        "provider": "smtp",
        "host": host,
        "port": port,
        "tls": env_flag("SMTP_USE_TLS", default=True),
        "sender": effective_sender,
        "configured": bool(username and password and effective_sender),
        "sender_matches_login": bool(username and effective_sender == username),
        "app_password_format_valid": (
            len(password) == 16 if host == "smtp.gmail.com" else bool(password)
        ),
    }


def send_email(to_email: str, subject: str, body: str) -> EmailResult:
    """Google App Password ile Gmail SMTP üzerinden işlem maili gönderir."""
    load_local_env()
    recipient = (to_email or "").strip()
    if not recipient:
        return EmailResult(False, "E-posta adresi bulunamadı")

    host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
    username = (os.environ.get("SMTP_USERNAME") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    configured_sender = (os.environ.get("SMTP_FROM") or username).strip()
    use_tls = env_flag("SMTP_USE_TLS", default=True)

    try:
        port = int((os.environ.get("SMTP_PORT") or "587").strip())
    except ValueError:
        mail_logger.error("mail_config_error reason=invalid_smtp_port")
        return EmailResult(False, "Mail gönderilemedi", "SMTP_PORT geçersiz")

    # Google App Password arayüzde dörderli gruplar halinde gösterilebilir.
    if host.lower() == "smtp.gmail.com":
        password = password.replace(" ", "")
        # Gmail doğrulanmış hesabın dışındaki From adreslerini reddedebilir veya
        # yeniden yazabilir. Tüm sistem maillerini oturum açılan hesaptan yollarız.
        sender = username
    else:
        sender = configured_sender

    if not username or not password or not sender:
        mail_logger.error(
            "mail_config_error provider=smtp host=%s username_set=%s "
            "password_set=%s sender_set=%s",
            host,
            bool(username),
            bool(password),
            bool(sender),
        )
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "SMTP ortam değişkenleri eksik",
        )

    message = EmailMessage()
    message["From"] = Address("Gümüş Veteriner", addr_spec=sender)
    message["Reply-To"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        mail_logger.error(
            "smtp_authentication_failed username=%s host=%s code=%s",
            username,
            host,
            exc.smtp_code,
        )
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "Gmail kullanıcı adı veya App Password kabul edilmedi",
        )
    except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
        mail_logger.error(
            "smtp_connection_failed host=%s port=%s tls=%s error_type=%s",
            host,
            port,
            use_tls,
            type(exc).__name__,
        )
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "SMTP sunucusuna bağlantı kurulamadı",
        )
    except Exception as exc:
        # Parola ve diğer secret değerler hiçbir zaman log mesajına eklenmez.
        mail_logger.exception(
            "smtp_send_failed recipient=%s host=%s port=%s tls=%s error=%s",
            recipient,
            host,
            port,
            use_tls,
            exc,
        )
        return EmailResult(False, "Mail gönderilemedi", str(exc))

    mail_logger.info(
        "smtp_send_success recipient=%s host=%s port=%s tls=%s",
        recipient,
        host,
        port,
        use_tls,
    )
    return EmailResult(True, "Mail gönderildi")
