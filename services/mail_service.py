from __future__ import annotations

import logging
import os
import smtplib
import ssl
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage

import requests

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
    gmail_api_configured = all(
        (os.environ.get(name) or "").strip()
        for name in (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GMAIL_REFRESH_TOKEN",
        )
    )
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
        "gmail_ssl_fallback": host == "smtp.gmail.com",
        "gmail_api_fallback_configured": gmail_api_configured,
    }


def _send_smtp_message(
    *,
    host: str,
    port: int,
    use_tls: bool,
    username: str,
    password: str,
    message: EmailMessage,
) -> str:
    """Mesajı seçilen SMTP taşımasıyla gönderir ve kullanılan yöntemi döndürür."""
    ssl_context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(
            host,
            port,
            timeout=20,
            context=ssl_context,
        ) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return "ssl"

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=ssl_context)
            smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)
    return "starttls" if use_tls else "plain"


def _send_gmail_api_message(message: EmailMessage) -> EmailResult:
    """SMTP erişilemezse Gmail API üzerinden aynı hesaptan mesaj gönderir."""
    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    refresh_token = (os.environ.get("GMAIL_REFRESH_TOKEN") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "Gmail API yedeği için GMAIL_REFRESH_TOKEN tanımlı değil",
        )

    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if token_response.status_code != 200:
            mail_logger.error(
                "gmail_api_token_failed status=%s",
                token_response.status_code,
            )
            return EmailResult(
                False,
                "Mail gönderilemedi",
                "Gmail API yetkilendirmesi yenilenemedi",
            )

        access_token = (token_response.json().get("access_token") or "").strip()
        if not access_token:
            mail_logger.error("gmail_api_token_missing")
            return EmailResult(
                False,
                "Mail gönderilemedi",
                "Gmail API erişim anahtarı alınamadı",
            )

        raw_message = urlsafe_b64encode(message.as_bytes()).decode("ascii")
        send_response = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw_message},
            timeout=20,
        )
        if send_response.status_code not in {200, 201}:
            mail_logger.error(
                "gmail_api_send_failed status=%s",
                send_response.status_code,
            )
            return EmailResult(
                False,
                "Mail gönderilemedi",
                "Gmail API mesajı kabul etmedi",
            )
    except requests.RequestException as exc:
        mail_logger.error(
            "gmail_api_connection_failed error_type=%s",
            type(exc).__name__,
        )
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "Gmail API bağlantısı kurulamadı",
        )
    except (TypeError, ValueError) as exc:
        mail_logger.error(
            "gmail_api_response_invalid error_type=%s",
            type(exc).__name__,
        )
        return EmailResult(
            False,
            "Mail gönderilemedi",
            "Gmail API geçersiz cevap döndürdü",
        )

    mail_logger.info("gmail_api_send_success recipient=%s", message["To"])
    return EmailResult(True, "Mail gönderildi")


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
        # Gmail doğrulanmış hesabın dışındaki From adreslerini reddedebilir.
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

    transport = ""
    effective_port = port
    try:
        transport = _send_smtp_message(
            host=host,
            port=port,
            use_tls=use_tls,
            username=username,
            password=password,
            message=message,
        )
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
        # Bazı hosting ağlarında STARTTLS 587 engellenebilir. Gmail'in güvenli
        # SSL 465 taşımasını otomatik yedek olarak deneriz.
        if host.lower() != "smtp.gmail.com" or port == 465:
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

        mail_logger.warning(
            "smtp_primary_connection_failed host=%s port=%s "
            "fallback_port=465 error_type=%s",
            host,
            port,
            type(exc).__name__,
        )
        try:
            transport = _send_smtp_message(
                host=host,
                port=465,
                use_tls=False,
                username=username,
                password=password,
                message=message,
            )
            effective_port = 465
        except smtplib.SMTPAuthenticationError as fallback_exc:
            mail_logger.error(
                "smtp_fallback_authentication_failed username=%s host=%s code=%s",
                username,
                host,
                fallback_exc.smtp_code,
            )
            return EmailResult(
                False,
                "Mail gönderilemedi",
                "Gmail kullanıcı adı veya App Password kabul edilmedi",
            )
        except (smtplib.SMTPConnectError, TimeoutError, OSError) as fallback_exc:
            mail_logger.error(
                "smtp_all_connections_failed host=%s ports=%s "
                "primary_error=%s fallback_error=%s",
                host,
                f"{port},465",
                type(exc).__name__,
                type(fallback_exc).__name__,
            )
            api_result = _send_gmail_api_message(message)
            if api_result.success:
                return api_result
            return EmailResult(
                False,
                "Mail gönderilemedi",
                (
                    "SMTP sunucusuna 587 ve 465 portlarından ulaşılamadı. "
                    f"{api_result.detail}"
                ),
            )
        except Exception as fallback_exc:
            mail_logger.exception(
                "smtp_fallback_send_failed recipient=%s host=%s "
                "port=465 error=%s",
                recipient,
                host,
                fallback_exc,
            )
            return EmailResult(
                False,
                "Mail gönderilemedi",
                "Gmail SSL bağlantısında gönderim hatası oluştu",
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
        "smtp_send_success recipient=%s host=%s port=%s tls=%s transport=%s",
        recipient,
        host,
        effective_port,
        use_tls,
        transport,
    )
    return EmailResult(True, "Mail gönderildi")
