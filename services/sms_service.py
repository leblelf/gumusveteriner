from __future__ import annotations

import os
import re
import xml.sax.saxutils as xml_escape
from dataclasses import dataclass

import requests


NETGSM_SEND_XML_URL = "https://api.netgsm.com.tr/sms/send/xml"
MAX_SMS_MESSAGE_LENGTH = 612
_ENV_LOADED = False


@dataclass(frozen=True)
class SmsResult:
    success: bool
    message: str
    provider_response: str = ""


def normalize_tr_phone(phone: str) -> str:
    """05XXXXXXXXX formatini dogrular ve Netgsm icin 5XXXXXXXXX formatina cevirir."""
    clean = re.sub(r"\s+", "", phone or "")
    if not re.fullmatch(r"05[0-9]{9}", clean):
        raise ValueError("Telefon numarası 05XXXXXXXXX formatında olmalı")
    return clean[1:]


def validate_sms_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        raise ValueError("Mesaj metni boş olamaz")
    if len(text) > MAX_SMS_MESSAGE_LENGTH:
        raise ValueError(f"Mesaj çok uzun. En fazla {MAX_SMS_MESSAGE_LENGTH} karakter gönderebilirsiniz")
    return text


def send_sms(phone: str, message: str) -> SmsResult:
    load_local_env()
    provider = (os.environ.get("SMS_PROVIDER") or "netgsm").strip().lower()
    if provider != "netgsm":
        return SmsResult(False, "SMS gönderilemedi", f"Desteklenmeyen SMS_PROVIDER: {provider}")

    usercode = (os.environ.get("NETGSM_USERCODE") or "").strip()
    password = (os.environ.get("NETGSM_PASSWORD") or "").strip()
    header = (os.environ.get("NETGSM_HEADER") or "").strip()
    if not usercode or not password or not header:
        return SmsResult(False, "SMS gönderilemedi", "Netgsm ortam değişkenleri eksik")

    gsm_no = normalize_tr_phone(phone)
    text = validate_sms_message(message)
    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<mainbody>
  <header>
    <company dil="TR">Netgsm</company>
    <usercode>{xml_escape.escape(usercode)}</usercode>
    <password>{xml_escape.escape(password)}</password>
    <type>1:n</type>
    <msgheader>{xml_escape.escape(header)}</msgheader>
  </header>
  <body>
    <msg><![CDATA[{text}]]></msg>
    <no>{gsm_no}</no>
  </body>
</mainbody>"""

    try:
        response = requests.post(
            NETGSM_SEND_XML_URL,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "application/xml; charset=utf-8"},
            timeout=20,
        )
    except requests.RequestException as exc:
        return SmsResult(False, "SMS gönderilemedi", str(exc))

    provider_text = response.text.strip()
    if response.ok and provider_text.startswith("00"):
        return SmsResult(True, "SMS gönderildi", provider_text)
    return SmsResult(False, "SMS gönderilemedi", provider_text)


def load_local_env() -> None:
    """Yerel calismada .env varsa okur; Railway'de zaten ortam degiskenleri gelir."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
