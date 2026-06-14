"""Eski import yollarını bozmamak için Gmail SMTP servisinin uyumluluk katmanı."""

from services.mail_service import (  # noqa: F401
    EmailResult,
    env_flag,
    get_mail_provider,
    mail_is_configured,
    send_email,
)
