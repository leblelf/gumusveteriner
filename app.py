from __future__ import annotations

"""
Gümüş Veteriner web uygulaması backend dosyası.

Bu dosya iki ana işi yapar:
1. SQLite veritabanını oluşturur ve randevu, üye, adres, hayvan, sipariş gibi
   verileri kaydeder.
2. Railway/Render/Gunicorn için Flask `app` nesnesini verir. Canlı ortam
   `gunicorn app:app` komutu ile buradaki `app` değişkenini çalıştırır.

Not: Dosyada eski stdlib HTTP handler yapısı korunuyor; Flask adaptörü altta bu
mevcut iş mantığını tekrar kullanır. Böylece önceki API kodları bozulmadan
deploy uyumlu hale gelir.
"""

import json
import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import threading
from functools import wraps
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, redirect, render_template, request, send_from_directory, session, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from services.mail_service import (
    EmailResult,
    env_flag,
    get_mail_provider,
    get_mail_status,
    mail_is_configured,
    send_email,
)
from services.database import normalize_database_url
from services.sms_service import load_local_env, send_sms, validate_sms_message, normalize_tr_phone


# ---------------------------------------------------------------------------
# Uygulama ayarları
# ---------------------------------------------------------------------------
# Dosya yolları, deploy bilgileri ve uygulama genel sabitleri burada durur.
# Render/Railway gibi servisler PORT değerini ortam değişkeni olarak verir.
ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = (ROOT / "data" / "gumus_veteriner.db").resolve()
DB_PATH = Path(
    os.environ.get("SQLITE_DB_PATH")
    or DEFAULT_DB_PATH
).resolve()
HOST = "0.0.0.0"
load_local_env()
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
PORT = int(os.environ.get("PORT", 5000))
IS_PRODUCTION = bool(os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT"))


def environment_secret(name: str) -> str:
    """Secret değerlerini production ortamında yalnızca Environment üzerinden alır."""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    if IS_PRODUCTION:
        raise RuntimeError(f"{name} Render Environment içinde tanımlanmalıdır.")
    # Local geliştirmede kaynak koda sabit bir secret yazmadan geçici anahtar üretir.
    return secrets.token_urlsafe(48)


SECRET_KEY = environment_secret("SECRET_KEY")
JWT_SECRET = (os.environ.get("JWT_SECRET") or SECRET_KEY).strip()
DEPLOY_VERSION = (
    os.environ.get("RENDER_GIT_COMMIT")
    or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("GIT_COMMIT")
    or "local"
)[:12]
SITE_URL = (os.environ.get("SITE_URL") or "https://wwwgumusvet.com").rstrip("/")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}
ALLOWED_UPLOAD_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
PET_HEALTH_RECORD_TYPES = {
    "disease": "Hastalık",
    "vaccine": "Aşı",
    "treatment": "Tedavi",
    "allergy": "Alerji",
    "medicine": "İlaç",
    "note": "Not",
}
DEFAULT_APPOINTMENT_TIMES = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
]

# Render/Railway ve Gunicorn bu değişkeni arar: `gunicorn app:app`.
app = Flask(__name__, static_folder=None)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SQLALCHEMY_DATABASE_URI=normalize_database_url(
        DATABASE_URL or f"sqlite:///{DB_PATH.as_posix()}"
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
    },
)
ALLOWED_CORS_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("CORS_ORIGIN", SITE_URL).split(",")
    if origin.strip()
}
CORS(
    app,
    resources={r"/api/*": {"origins": list(ALLOWED_CORS_ORIGINS)}},
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per hour", "120 per minute"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
oauth = OAuth(app)
GOOGLE_OAUTH_REGISTERED = False
Talisman(
    app,
    force_https=IS_PRODUCTION,
    frame_options="DENY",
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy=None,  # CSP aşağıdaki ortak response katmanında yönetilir.
)
sqlalchemy_db = SQLAlchemy(app)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
security_logger = logging.getLogger("gumus_veteriner.security")
_DB_INIT_LOCK = threading.Lock()
_DB_INITIALIZED = False


def ensure_database_directory() -> None:
    """SQLite klasörü yazılamıyorsa deploy'u ayakta tutmak için local klasöre döner."""
    global DB_PATH
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if DB_PATH == DEFAULT_DB_PATH:
            raise
        security_logger.exception(
            "sqlite_persistent_path_unavailable fallback=%s requested=%s",
            DEFAULT_DB_PATH,
            DB_PATH,
        )
        DB_PATH = DEFAULT_DB_PATH
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    """DATABASE_URL varsa PostgreSQL'e, yoksa local SQLite dosyasına bağlanır."""
    if DATABASE_URL:
        from services.postgres_adapter import PostgresConnection

        return PostgresConnection(DATABASE_URL)
    ensure_database_directory()
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def init_db() -> None:
    """Uygulama için gereken tüm tablolar yoksa oluşturulur."""
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        # SQL şeması tek yerde tutuluyor. Yeni tablo/kolon eklerken önce buraya
        # bak; uygulama açılışında eksik yapılar otomatik tamamlanır.
        db.executescript(
            """
            DROP TRIGGER IF EXISTS prevent_duplicate_user_email_insert;
            DROP TRIGGER IF EXISTS prevent_duplicate_user_email_update;

            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                pet_id INTEGER,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                pet_type TEXT NOT NULL,
                pet_name TEXT,
                service TEXT NOT NULL,
                appt_date TEXT NOT NULL,
                appt_time TEXT NOT NULL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_hidden INTEGER NOT NULL DEFAULT 0,
                admin_pet_hidden INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(pet_id) REFERENCES pets(id)
            );

            CREATE TRIGGER IF NOT EXISTS prevent_duplicate_active_appointments_insert
            BEFORE INSERT ON appointments
            WHEN EXISTS (
                SELECT 1 FROM appointments
                WHERE appt_date = NEW.appt_date
                  AND appt_time = NEW.appt_time
                  AND status NOT IN ('cancelled')
            )
            BEGIN
                SELECT RAISE(ABORT, 'DUPLICATE_APPOINTMENT_SLOT');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_duplicate_active_appointments_update
            BEFORE UPDATE OF appt_date, appt_time, status ON appointments
            WHEN NEW.status NOT IN ('cancelled') AND EXISTS (
                SELECT 1 FROM appointments
                WHERE id <> NEW.id
                  AND appt_date = NEW.appt_date
                  AND appt_time = NEW.appt_time
                  AND status NOT IN ('cancelled')
            )
            BEGIN
                SELECT RAISE(ABORT, 'DUPLICATE_APPOINTMENT_SLOT');
            END;

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                image_url TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                address TEXT NOT NULL,
                notes TEXT,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_hidden INTEGER NOT NULL DEFAULT 0,
                payment_last4 TEXT,
                payment_status TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT,
                message TEXT NOT NULL,
                reply TEXT,
                replied_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                full_name TEXT NOT NULL,
                name TEXT,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                profile_picture TEXT,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                is_banned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS password_resets (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT,
                district TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                species TEXT NOT NULL,
                age TEXT,
                notes TEXT,
                admin_hidden INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS clinic_pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                appointment_id INTEGER,
                name TEXT NOT NULL,
                species TEXT NOT NULL,
                breed TEXT,
                age TEXT,
                owner_name TEXT,
                phone TEXT,
                notes TEXT,
                admin_hidden INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(appointment_id) REFERENCES appointments(id)
            );

            CREATE TABLE IF NOT EXISTS hospitalizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER,
                clinic_pet_id INTEGER,
                appointment_id INTEGER,
                user_id INTEGER,
                pet_name TEXT NOT NULL,
                species TEXT,
                owner_name TEXT,
                phone TEXT,
                room TEXT,
                diagnosis TEXT NOT NULL,
                treatment TEXT NOT NULL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                admitted_at TEXT NOT NULL,
                discharged_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pet_id) REFERENCES pets(id),
                FOREIGN KEY(clinic_pet_id) REFERENCES clinic_pets(id),
                FOREIGN KEY(appointment_id) REFERENCES appointments(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS pet_health_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                record_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT,
                record_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pet_id) REFERENCES pets(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS appointment_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(appointment_id) REFERENCES appointments(id)
            );

            CREATE TABLE IF NOT EXISTS appointment_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appt_date TEXT NOT NULL,
                appt_time TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(appt_date, appt_time)
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_username TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_texts (
                text_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                author TEXT NOT NULL,
                pet_type TEXT,
                product_name TEXT,
                rating INTEGER NOT NULL DEFAULT 5,
                message TEXT NOT NULL,
                reply TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                reference_type TEXT,
                reference_id INTEGER,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        seed_admin(db)
        seed_api_admin(db)
        seed_site_content(db)
        seed_legacy_hospitalizations(db)
        ensure_column(db, "users", "is_banned", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "users", "google_id", "TEXT")
        ensure_column(db, "users", "name", "TEXT")
        ensure_column(db, "users", "profile_picture", "TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL")
        ensure_column(db, "orders", "user_id", "INTEGER")
        ensure_column(db, "appointments", "user_id", "INTEGER")
        ensure_column(db, "appointments", "pet_id", "INTEGER")
        ensure_column(db, "appointments", "clinic_pet_id", "INTEGER")
        ensure_column(db, "orders", "payment_last4", "TEXT")
        ensure_column(db, "orders", "payment_status", "TEXT")
        ensure_column(db, "orders", "admin_hidden", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "appointments", "admin_hidden", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "appointments", "admin_pet_hidden", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "pets", "admin_hidden", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "clinic_pets", "admin_hidden", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "contacts", "reply", "TEXT")
        ensure_column(db, "contacts", "replied_at", "TEXT")
        ensure_column(db, "site_reviews", "product_name", "TEXT")
        ensure_column(db, "site_reviews", "user_id", "INTEGER")
        db.commit()


def ensure_database_initialized() -> None:
    """Tablo kurulumunu worker başına yalnızca bir kez çalıştırır."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with _DB_INIT_LOCK:
        if _DB_INITIALIZED:
            return
        if not DATABASE_URL:
            ensure_database_directory()
        try:
            init_db()
        except Exception:
            if DATABASE_URL:
                # PostgreSQL şeması kurulamazsa deploy açıkça hata vermeli.
                # Eksik tablolarla çalışmak sessiz veri kaybına yol açabilir.
                security_logger.exception("postgres_database_init_failed")
                raise
            # Eski production veritabanında beklenmeyen bir migration uyumsuzluğu
            # varsa mevcut tablolarla siteyi çalışır tut. Hata loglarda kalır ve
            # sonraki deploy öncesinde ayrıca incelenebilir.
            security_logger.exception("database_init_failed_using_existing_schema")
        _DB_INITIALIZED = True


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Eski veritabanlarina yeni kolon eklemek için güvenli migration yardımcısı."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Geçersiz tablo adı")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
        raise ValueError("Geçersiz kolon adı")
    if not re.fullmatch(r"[A-Za-z0-9_ ()'.,-]+", definition):
        raise ValueError("Geçersiz kolon tanımı")
    columns = (
        db.table_columns(table)
        if hasattr(db, "table_columns")
        else {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    )
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def first_column(row):
    """SQLite Row ve PostgreSQL RealDictRow içinden ilk sütun değerini alır."""
    if hasattr(row, "values"):
        return next(iter(row.values()))
    return row[0]


def get_csrf_token() -> str:
    """Browser tabanlı formlar için session'a bağlı CSRF token üretir."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_required_for_request() -> bool:
    """Tarayicidan gelen state-changing isteklerde CSRF kontrolunu zorunlu tutar."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return False
    if not request.path.startswith("/api/"):
        return False
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return False
    # Mobil/masaüstü uygulamalar Origin/Referer göndermeyebilir; CSRF tarayıcı yüzeyi içindir.
    return bool(request.headers.get("Origin") or request.headers.get("Referer"))


def validate_upload_file(file_storage) -> str:
    """Dosya yukleme acilirsa uzanti, mime type ve dosya adini güvenli hale getirir."""
    filename = secure_filename(file_storage.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mimetype = (file_storage.mimetype or "").lower()
    if not filename or extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Desteklenmeyen dosya uzantısı")
    if mimetype not in ALLOWED_UPLOAD_MIME_TYPES:
        raise ValueError("Desteklenmeyen dosya türü")
    return filename


def log_admin_login_attempt(username: str, success: bool) -> None:
    """Admin giriş denemelerini hem log dosyasina hem veritabanına yazar."""
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:250]
    security_logger.info("admin_login username=%s success=%s ip=%s", username, success, ip_address)
    try:
        with connect() as db:
            db.execute(
                """
                INSERT INTO admin_login_attempts (username, ip_address, user_agent, success, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, ip_address, user_agent, 1 if success else 0, datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
    except Exception:
        security_logger.exception("admin_login_attempt_log_failed")


def log_admin_action(action: str, target_type: str = "", target_id: str | int = "", details: str = "") -> None:
    """Admin uygulamasındaki kritik değişiklikleri güvenlik kaydına ekler."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    payload = decode_admin_jwt(token) if token else None
    username = (payload or {}).get("username", "unknown")
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    security_logger.info(
        "admin_action username=%s action=%s target=%s:%s ip=%s",
        username,
        action,
        target_type,
        target_id,
        ip_address,
    )
    try:
        with connect() as db:
            db.execute(
                """
                INSERT INTO admin_audit_logs
                (admin_username, action, target_type, target_id, details, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    action,
                    target_type,
                    str(target_id),
                    details[:500],
                    ip_address,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            db.commit()
    except Exception:
        security_logger.exception("admin_action_log_failed")


def validate_phone(phone: str) -> str:
    """Telefonu 05XXXXXXXXX formatında zorunlu ve temiz hale getirir."""
    clean = re.sub(r"\s+", "", phone or "")
    if not re.fullmatch(r"0[0-9]{10}", clean):
        raise ValueError("Gecerli telefon: 05XX XXX XX XX")
    return clean


def validate_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("Gecerli bir email girin")
    return value


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Şifreleri düz metin yerine Werkzeug hash olarak saklar."""
    if len(password or "") < 6:
        raise ValueError("Şifre en az 6 karakter olmalı")
    return generate_password_hash(password), "werkzeug"


def hash_reset_token(token: str) -> str:
    """Şifre sıfırlama tokenını veritabanında düz metin yerine SHA-256 olarak saklar."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    """Yeni Werkzeug hashlerini ve eski PBKDF2 kayıtlarını doğrular."""
    if password_salt == "werkzeug" or password_hash.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(password_hash, password)
    legacy_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(password_salt), 120_000)
    return hmac.compare_digest(legacy_digest.hex(), password_hash)


def seed_admin(db: sqlite3.Connection) -> None:
    """İlk kurulumda Environment üzerinden verilen admin hesabını oluşturur."""
    email = (os.environ.get("INITIAL_ADMIN_EMAIL") or "").strip().lower()
    initial_password = (os.environ.get("INITIAL_ADMIN_PASSWORD") or "").strip()
    if not email:
        security_logger.warning("initial_admin_skipped INITIAL_ADMIN_EMAIL tanımlı değil")
        return
    old_email = "admin@gumusveteriner.com"
    now = datetime.now().isoformat(timespec="seconds")
    current = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    old = db.execute("SELECT id FROM users WHERE email = ?", (old_email,)).fetchone()
    if current:
        db.execute(
            "UPDATE users SET full_name = ?, role = 'admin', is_banned = 0 WHERE id = ?",
            ("Gümüş Veteriner Muayenehanesi", current["id"]),
        )
        return
    if old:
        db.execute(
            """
            UPDATE users
            SET full_name = ?, email = ?, role = 'admin', is_banned = 0
            WHERE id = ?
            """,
            ("Gümüş Veteriner Muayenehanesi", email, old["id"]),
        )
        return
    if not initial_password:
        security_logger.warning("initial_admin_skipped INITIAL_ADMIN_PASSWORD tanımlı değil")
        return
    password_hash, password_salt = hash_password(initial_password)
    db.execute(
        """
        INSERT INTO users (full_name, email, phone, password_hash, password_salt, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("Gümüş Veteriner Muayenehanesi", email, "", password_hash, password_salt, "admin", now),
    )


def seed_api_admin(db: sqlite3.Connection) -> None:
    """Mobil/masaüstü admin uygulaması için ilk JWT admin hesabını oluşturur."""
    username = (os.environ.get("INITIAL_ADMIN_EMAIL") or "").strip().lower()
    initial_password = (os.environ.get("INITIAL_ADMIN_PASSWORD") or "").strip()
    if not username:
        security_logger.warning("initial_api_admin_skipped INITIAL_ADMIN_EMAIL tanımlı değil")
        return
    legacy_username = "admin"
    current = db.execute("SELECT id FROM admins WHERE username = ?", (username,)).fetchone()
    legacy = db.execute("SELECT id FROM admins WHERE username = ?", (legacy_username,)).fetchone()
    if current:
        if legacy:
            db.execute("DELETE FROM admins WHERE id = ?", (legacy["id"],))
        return
    if legacy:
        db.execute(
            "UPDATE admins SET username = ? WHERE id = ?",
            (username, legacy["id"]),
        )
        return
    if not initial_password:
        security_logger.warning("initial_api_admin_skipped INITIAL_ADMIN_PASSWORD tanımlı değil")
        return
    default_hash = generate_password_hash(initial_password)
    db.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", (username, default_hash))


def seed_site_content(db: sqlite3.Connection) -> None:
    """Admin uygulamasından yönetilecek site metinleri ve yorumları için ilk veriler."""
    now = datetime.now().isoformat(timespec="seconds")
    texts = [
        ("hero_title", "Ana sayfa başlığı", "Dostlarınız İçin\nEn Güvenilir Bakım"),
        ("hero_subtitle", "Ana sayfa açıklaması", "Toptepe, Kayaaltı Sk. No:10/1, Canik/Samsun adresinde 24 saat açık veteriner hizmeti."),
        ("home_services_title", "Ana sayfa hizmetler başlığı", "Hizmetlerimiz"),
        ("home_services_subtitle", "Ana sayfa hizmetler açıklaması", "Evcil dostlarınız için kapsamlı veteriner hizmetleri"),
        ("home_products_title", "Ana sayfa ürünler başlığı", "Öne Çıkan Ürünler"),
        ("home_products_subtitle", "Ana sayfa ürünler açıklaması", "Evcil hayvanınız için seçilmiş ürünler"),
        ("home_reviews_title", "Ana sayfa yorumlar başlığı", "Müşteri Yorumları"),
        ("home_reviews_subtitle", "Ana sayfa yorumlar açıklaması", "Evcil hayvan sahiplerinin deneyimleri"),
        ("about_title", "Hakkımızda başlığı", "Hakkımızda"),
        ("about_subtitle", "Hakkımızda alt başlığı", "Samsun Gümüş Veteriner Muayenehanesi"),
        ("about_intro", "Hakkımızda bilgi kutusu", "Samsun'da evcil dostlarınız için muayene, koruyucu sağlık, randevu ve pet ürünleri süreçlerini tek ekranda yöneten modern klinik deneyimi."),
        ("services_title", "Hizmetler başlığı", "Hizmetlerimiz"),
        ("services_subtitle", "Hizmetler açıklaması", "Evcil hayvanlarınız için kapsamlı veteriner hizmetleri"),
        ("appointment_title", "Randevu başlığı", "Online Randevu"),
        ("appointment_subtitle", "Randevu açıklaması", "Kolayca randevu alın, SMS ile onaylayalım"),
        ("appointment_info", "Randevu bilgi kutusu", "Randevunuz en geç 2 saat içinde SMS ile onaylanır. İptal için 24 saat önce haber vermeniz yeterli."),
        ("blog_title", "Blog başlığı", "Blog & Bilgilendirme"),
        ("blog_subtitle", "Blog açıklaması", "Evcil hayvan sağlığı hakkında uzman bilgileri"),
        ("blog_1_tag", "Blog 1 kategori", "Köpek Sağlığı"),
        ("blog_1_title", "Blog 1 başlık", "Yıllık Aşı Takvimi Neden Önemli?"),
        ("blog_1_meta", "Blog 1 bilgi", "Dr. Ahmet Yılmaz • 5 dk okuma"),
        ("blog_2_tag", "Blog 2 kategori", "Kedi Sağlığı"),
        ("blog_2_title", "Blog 2 başlık", "Kedilerde Diş Sağlığı: Evde Bakım Tüyoleri"),
        ("blog_2_meta", "Blog 2 bilgi", "Dr. Fatma Öztürk • 4 dk okuma"),
        ("blog_3_tag", "Blog 3 kategori", "Genel Bakım"),
        ("blog_3_title", "Blog 3 başlık", "Tavşanlar İçin Doğru Beslenme Rehberi"),
        ("blog_3_meta", "Blog 3 bilgi", "Dr. Can Arslan • 6 dk okuma"),
        ("blog_4_tag", "Blog 4 kategori", "Kısırlaştırma"),
        ("blog_4_title", "Blog 4 başlık", "Kısırlaştırma: Doğru Zamanlama ve Sonrası"),
        ("blog_4_meta", "Blog 4 bilgi", "Dr. Ahmet Yılmaz • 7 dk okuma"),
        ("blog_5_tag", "Blog 5 kategori", "Parazit Koruma"),
        ("blog_5_title", "Blog 5 başlık", "Pire ve Kene Tedavisinde Doğru Ürün"),
        ("blog_5_meta", "Blog 5 bilgi", "Dr. Fatma Öztürk • 3 dk okuma"),
        ("blog_6_tag", "Blog 6 kategori", "Acil Durumlar"),
        ("blog_6_title", "Blog 6 başlık", "Evcil Hayvanımda Acil Durum mu?"),
        ("blog_6_meta", "Blog 6 bilgi", "Dr. Can Arslan • 5 dk okuma"),
        ("contact_title", "İletişim başlığı", "İletişim"),
        ("contact_subtitle", "İletişim açıklaması", "Her türlü soru için buradayız"),
        ("footer_title", "Footer klinik adı", "Samsun Gümüş Veteriner Muayenehanesi"),
        ("footer_rights", "Footer hak metni", "© 2026 Samsun Gümüş Veteriner Muayenehanesi. Tüm hakları saklıdır."),
    ]
    for key, label, value in texts:
        db.execute(
            """
            INSERT OR IGNORE INTO site_texts (text_key, label, value, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, label, value, now),
        )

    if not db.execute("SELECT 1 FROM site_reviews LIMIT 1").fetchone():
        rows = [
            ("Ayşe K.", "Kedi Sahibi", 5, "Miyav'ımın aşı randevusu çok sorunsuz geçti. Ekip gerçekten ilgili ve şefkatli.", "Güzel yorumunuz için teşekkür ederiz."),
            ("Mehmet T.", "Köpek Sahibi", 5, "Köpeğimiz Max'in ameliyatı için çok endişeliydik. Her adımda bilgi verdiler.", "Max'e sağlıklı günler dileriz."),
            ("Zeynep A.", "Tavşan Sahibi", 4, "Online randevu sistemi çok kullanışlı. Bekleme süresi kısa, klinik temiz.", ""),
        ]
        db.executemany(
            """
            INSERT INTO site_reviews (author, pet_type, rating, message, reply, active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            [(author, pet_type, rating, message, reply, now) for author, pet_type, rating, message, reply in rows],
        )


def seed_legacy_hospitalizations(db: sqlite3.Connection) -> None:
    """Eski masaüstü uygulamasındaki aktif yatışları bir kez veritabanına taşır."""
    admitted_at = "2026-05-25T09:00:00"
    legacy_rows = [
        (
            "GÜMÜŞ VET - Luna",
            "Kedi",
            "DAMLA TOKUR",
            "5466696329",
            "Oda 1",
            "Serum ve gözlem",
            "Sıvı tedavisi, ateş takibi ve 4 saatte bir genel durum kontrolü",
            "İştah ve su tüketimi takip edilecek.",
        ),
        (
            "Tyson",
            "Köpek",
            "AHMET TOK",
            "5422031281",
            "Oda 2",
            "Operasyon sonrası takip",
            "Ağrı kontrolü, pansuman ve antibiyotik protokolü",
            "Dikiş bölgesi sabah akşam kontrol edilecek.",
        ),
        (
            "ZEYTİN",
            "Kedi",
            "ELİF GÜVEN",
            "5388388949",
            "Oda 3",
            "Ateş ve iştahsızlık",
            "Ateş düşürücü destek, kan tahlili kontrolü ve beslenme takibi",
            "24 saat gözlem önerildi.",
        ),
    ]
    for pet_name, species, owner, phone, room, diagnosis, treatment, notes in legacy_rows:
        existing = db.execute(
            """
            SELECT 1 FROM hospitalizations
            WHERE LOWER(pet_name) = LOWER(?) AND diagnosis = ?
            LIMIT 1
            """,
            (pet_name, diagnosis),
        ).fetchone()
        if existing:
            continue
        db.execute(
            """
            INSERT INTO hospitalizations
            (pet_name, species, owner_name, phone, room, diagnosis, treatment,
             notes, status, admitted_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                pet_name,
                species,
                owner,
                phone,
                room,
                diagnosis,
                treatment,
                notes,
                admitted_at,
                admitted_at,
            ),
        )


def validate_appointment(data: dict) -> dict:
    """Randevu formundan gelen zorunlu alanlari ve tarih araligini kontrol eder."""
    required = ["first_name", "last_name", "phone", "pet_type", "service", "appt_date", "appt_time"]
    for field in required:
        if not str(data.get(field, "")).strip():
            raise ValueError(f"{field} alani zorunlu")

    data["phone"] = validate_phone(data["phone"])
    try:
        selected = datetime.strptime(data["appt_date"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Tarih YYYY-MM-DD formatında olmalı") from exc

    if selected < date.today():
        raise ValueError("Gecmis tarih secilemez")
    if selected > date.today() + timedelta(days=60):
        raise ValueError("En fazla 60 gün ileriye randevu alinabilir")
    if not re.fullmatch(r"\d{2}:\d{2}", str(data.get("appt_time", ""))):
        raise ValueError("Saat HH:MM formatında olmalı")
    return data


def apply_member_appointment_defaults(data: dict, user: sqlite3.Row | None) -> dict:
    """Üye girişi varsa randevu formunda kişisel bilgileri otomatik tamamlar."""
    if not user:
        return data
    prepared = dict(data)
    full_name = (user["full_name"] or "Üye").strip()
    parts = full_name.split()
    prepared["first_name"] = prepared.get("first_name") or (parts[0] if parts else "Üye")
    prepared["last_name"] = prepared.get("last_name") or (" ".join(parts[1:]) if len(parts) > 1 else "Gumus")
    prepared["phone"] = prepared.get("phone") or (user["phone"] or "")
    prepared["email"] = prepared.get("email") or (user["email"] or "")
    prepared["pet_type"] = prepared.get("pet_type") or "Belirtilmedi"
    prepared["service"] = prepared.get("service") or "Genel Muayene"
    return prepared


def appointment_slot_summary(db: sqlite3.Connection, appt_date: str) -> list[dict]:
    """Bir gün için MHRS benzeri boş/dolu/kapalı saat listesini hazırlar."""
    slots = {
        row["appt_time"]: row
        for row in db.execute(
            "SELECT * FROM appointment_slots WHERE appt_date = ?",
            (appt_date,),
        ).fetchall()
    }
    taken = {
        row["appt_time"]
        for row in db.execute(
            """
            SELECT appt_time FROM appointments
            WHERE appt_date = ? AND status NOT IN ('cancelled')
            """,
            (appt_date,),
        ).fetchall()
    }
    explicit_times = sorted(set(slots) - set(DEFAULT_APPOINTMENT_TIMES))
    rows = []
    for appt_time in [*DEFAULT_APPOINTMENT_TIMES, *explicit_times]:
        slot = slots.get(appt_time)
        blocked = bool(slot and not slot["is_available"])
        is_taken = appt_time in taken
        rows.append(
            {
                "date": appt_date,
                "time": appt_time,
                "available": not blocked and not is_taken,
                "taken": is_taken,
                "blocked": blocked,
                "note": slot["note"] if slot else "",
            }
        )
    return rows


def is_appointment_time_available(db: sqlite3.Connection, appt_date: str, appt_time: str) -> bool:
    """Aynı tarih/saat için ikinci aktif randevuyu engeller."""
    rows = appointment_slot_summary(db, appt_date)
    match = next((row for row in rows if row["time"] == appt_time), None)
    return bool(match and match["available"])


def get_request_session_user() -> sqlite3.Row | None:
    """Flask route'larında Authorization token'ı ile üye bilgisini bulur."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = session.get("session_token", "")
    if not token:
        return None
    with connect() as db:
        return db.execute(
            """
            SELECT users.id, users.google_id, users.full_name, users.name, users.email, users.phone,
                   users.profile_picture, users.role, users.created_at, users.is_banned
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()


def add_user_notification(
    db: sqlite3.Connection,
    user_id: int | None,
    kind: str,
    title: str,
    message: str,
    reference_type: str = "",
    reference_id: int | None = None,
) -> None:
    """Admin işlemlerinden sonra üyeye üst menüde gösterilecek bildirim ekler."""
    if not user_id:
        return
    db.execute(
        """
        INSERT INTO notifications
          (user_id, kind, title, message, reference_type, reference_id, is_read, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            user_id,
            kind,
            title[:120],
            message[:500],
            reference_type[:40],
            reference_id,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def create_user_session(db: sqlite3.Connection, user: sqlite3.Row, remember: bool = False) -> str:
    """Kullanıcı için hem veritabanı token'ı hem Flask session kaydı oluşturur."""
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (token, user_id, role, created_at) VALUES (?, ?, ?, ?)",
        (token, user["id"], user["role"], datetime.now().isoformat(timespec="seconds")),
    )
    session.permanent = remember
    session["user_id"] = user["id"]
    session["session_token"] = token
    session["role"] = user["role"]
    return token


def login_required(view):
    """Flask route'ları için basit üye girişi koruması."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_request_session_user()
        if not user:
            return redirect(url_for("serve_app_index"))
        return view(*args, **kwargs)
    return wrapped


class UserModel:
    """Google ve klasik üye kayıtlarının aynı users tablosunda tutulmasını sağlar."""

    @staticmethod
    def find_by_google_or_email(db: sqlite3.Connection, google_id: str, email: str) -> sqlite3.Row | None:
        return db.execute(
            "SELECT * FROM users WHERE google_id = ? OR LOWER(email) = LOWER(?) ORDER BY google_id = ? DESC LIMIT 1",
            (google_id, email, google_id),
        ).fetchone()

    @staticmethod
    def upsert_google_user(db: sqlite3.Connection, profile: dict) -> sqlite3.Row:
        google_id = str(profile.get("sub") or "").strip()
        email = validate_email(profile.get("email") or "")
        name = (profile.get("name") or email.split("@")[0]).strip()
        picture = (profile.get("picture") or "").strip()
        if not google_id:
            raise ValueError("Google kullanıcı kimligi alinamadi")

        existing = UserModel.find_by_google_or_email(db, google_id, email)
        if existing:
            db.execute(
                """
                UPDATE users
                SET google_id = ?, full_name = ?, name = ?, profile_picture = ?
                WHERE id = ?
                """,
                (google_id, name, name, picture, existing["id"]),
            )
            return db.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()

        password_hash, password_salt = hash_password(secrets.token_urlsafe(24))
        cursor = db.execute(
            """
            INSERT INTO users
              (google_id, full_name, name, email, phone, profile_picture, password_hash, password_salt, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'member', ?)
            """,
            (
                google_id,
                name,
                name,
                email,
                "",
                picture,
                password_hash,
                password_salt,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()


def ensure_google_oauth():
    """Google OAuth istemcisini ortam değişkenleri varsa kaydeder."""
    global GOOGLE_OAUTH_REGISTERED
    load_local_env()
    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return None
    if not GOOGLE_OAUTH_REGISTERED:
        oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        GOOGLE_OAUTH_REGISTERED = True
    return oauth.google


def order_with_items(db: sqlite3.Connection, order_id: int) -> dict | None:
    order = db.execute(
        """
        SELECT orders.*,
               COALESCE(NULLIF(orders.email, ''), users.email) AS notification_email
        FROM orders
        LEFT JOIN users ON users.id = orders.user_id
        WHERE orders.id = ?
        """,
        (order_id,),
    ).fetchone()
    if not order:
        return None
    payload = row_to_dict(order)
    payload["items"] = [
        row_to_dict(row)
        for row in db.execute(
            """
            SELECT order_items.product_id, products.name, order_items.quantity, order_items.unit_price
            FROM order_items
            LEFT JOIN products ON products.id = order_items.product_id
            WHERE order_items.order_id = ?
            ORDER BY order_items.id
            """,
            (order_id,),
        ).fetchall()
    ]
    return payload


def appointment_with_contact(
    db: sqlite3.Connection,
    appointment_id: int,
) -> dict | None:
    """Randevuyu, bildirim için kullanılabilecek üyelik e-postasıyla birlikte getirir."""
    appointment = db.execute(
        """
        SELECT appointments.*,
               COALESCE(NULLIF(appointments.email, ''), users.email) AS notification_email
        FROM appointments
        LEFT JOIN users ON users.id = appointments.user_id
        WHERE appointments.id = ?
        """,
        (appointment_id,),
    ).fetchone()
    return row_to_dict(appointment) if appointment else None


def send_order_status_email(order: dict, status: str) -> EmailResult:
    recipient = (
        order.get("notification_email")
        or order.get("email")
        or ""
    ).strip()
    if not recipient:
        return EmailResult(
            False,
            "E-posta gönderilemedi",
            "Siparişe veya kullanıcı hesabına kayıtlı e-posta adresi yok",
        )
    status_text = {
        "confirmed": "onaylandı ve hazırlanıyor",
        "shipped": "kargoya verildi",
        "delivered": "teslim edildi",
        "cancelled": "iptal edildi",
    }.get(status)
    if not status_text:
        return EmailResult(
            False,
            "E-posta gönderilmedi",
            "Bu sipariş durumu için e-posta bildirimi tanımlı değil",
        )
    subject = f"Gümüş Veteriner siparişiniz {status_text} - #{order['id']}"
    body = (
        f"Merhaba {order.get('first_name', '')},\n\n"
        f"#{order['id']} numaralı siparişiniz {status_text}.\n"
        + ("Kargonuz teslimat sürecine alınmıştır.\n" if status == "shipped" else "")
        + "\n"
        "Gümüş Veteriner Muayenehanesi\n"
        "0546 136 14 33"
    )
    return send_email(recipient, subject, body)


def send_appointment_status_email(
    appointment: dict,
    status: str,
) -> EmailResult:
    """Randevu durumu değiştiğinde müşteriye güvenli bir bilgilendirme maili gönderir."""
    recipient = (
        appointment.get("notification_email")
        or appointment.get("email")
        or ""
    ).strip()
    if not recipient:
        return EmailResult(
            False,
            "E-posta gönderilemedi",
            "Randevuya veya kullanıcı hesabına kayıtlı e-posta adresi yok",
        )
    status_text = {
        "pending": "onay bekliyor olarak güncellendi",
        "confirmed": "onaylandı",
        "cancelled": "iptal edildi",
        "completed": "tamamlandı",
    }.get(status)
    if not status_text:
        return EmailResult(
            False,
            "E-posta gönderilmedi",
            "Bu randevu durumu için e-posta bildirimi tanımlı değil",
        )
    subject = f"Gümüş Veteriner randevunuz {status_text}"
    body = (
        f"Merhaba {appointment.get('first_name', '')},\n\n"
        f"{appointment.get('appt_date', '')} tarihinde "
        f"{appointment.get('appt_time', '')} saatindeki "
        f"randevunuz {status_text}.\n"
        f"Hizmet: {appointment.get('service') or 'Veteriner muayenesi'}\n"
        f"Hayvan: {appointment.get('pet_name') or appointment.get('pet_type') or '-'}\n\n"
        "Gümüş Veteriner Muayenehanesi\n"
        "0546 136 14 33"
    )
    return send_email(recipient, subject, body)


def api_response(success: bool, message: str, data=None, status: HTTPStatus = HTTPStatus.OK):
    """Web ve admin uygulamasının beklediği standart JSON cevap formatı."""
    return {"success": success, "message": message, "data": data}, int(status)


def create_admin_jwt(admin_id: int, username: str) -> str:
    """Admin API için 7 gün geçerli JWT token üretir."""
    payload = {
        "sub": str(admin_id),
        "username": username,
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_admin_jwt(token: str) -> dict | None:
    """Authorization header içindeki JWT token'ı çözer."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("role") != "admin":
        return None
    return payload


def require_admin_api(func):
    """Flask admin API endpointlerini JWT ile koruyan decorator."""
    @limiter.limit("60 per minute")
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        payload = decode_admin_jwt(token)
        if not payload:
            body, status = api_response(False, "Admin yetkisi gerekli", None, HTTPStatus.UNAUTHORIZED)
            return body, status
        return func(*args, **kwargs)
    return wrapper


class GumusVeterinerHandler(SimpleHTTPRequestHandler):
    """Eski saf-Python HTTP handler.

    Proje ilk başlarda Flask olmadan yazıldığı için bazı iş kuralları burada
    duruyor. Alttaki Flask adapter bu metotları kullanarak eski davranışı
    koruyor. Bu sayede web sitesi ve admin API'leri yeniden yazilmadan deploy
    edilebilir hale geldi.
    """

    """Eski local sunucu/API iş mantığı.

    Bu sınıf randevu, sipariş, üye, admin ve profil API'lerini yönetir.
    Flask adaptörü bu metotları tekrar kullanarak Railway/Render üzerinde de
    aynı davranışın çalışmasını sağlar.
    """

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path in {"/", "/admin/login", "/admin", "/403"}:
            return str(ROOT / "templates" / "index.html")
        return str(ROOT / parsed.path.lstrip("/"))

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_CORS_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed)
            return
        if parsed.path.startswith("/admin") or parsed.path == "/403":
            self.serve_index()
            return
        super().do_GET()

    def serve_index(self) -> None:
        data = (ROOT / "templates" / "index.html").read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/appointments":
            self.create_appointment()
            return
        if parsed.path == "/api/reviews":
            self.create_purchase_review()
            return
        if parsed.path == "/api/orders":
            self.create_order()
            return
        if parsed.path == "/api/contact":
            self.create_contact()
            return
        if parsed.path == "/api/register":
            self.create_user()
            return
        if parsed.path == "/api/login":
            self.login_user(required_role="member")
            return
        if parsed.path == "/api/admin/login":
            self.login_user(required_role="admin")
            return
        if parsed.path == "/api/logout":
            self.logout_user()
            return
        if parsed.path in {"/api/profile/addresses", "/api/profile/address", "/api/addresses", "/api/address"}:
            self.create_address()
            return
        if parsed.path in {"/api/profile/pets", "/api/profile/pet", "/api/pets", "/api/pet"}:
            self.create_pet()
            return
        self.send_json({"error": "Endpoint bulunamadi"}, HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:
        if not self.require_admin():
            return
        parsed = urlparse(self.path)
        user_match = re.fullmatch(r"/api/admin/users/(\d+)", parsed.path)
        if user_match:
            self.update_admin_user(int(user_match.group(1)))
            return
        match = re.fullmatch(r"/api/appointments/(\d+)/status", parsed.path)
        if not match:
            self.send_json({"error": "Endpoint bulunamadi"}, HTTPStatus.NOT_FOUND)
            return

        status = parse_qs(parsed.query).get("status", [""])[0]
        if status not in {"pending", "confirmed", "cancelled", "completed"}:
            self.send_json({"error": "Geçersiz durum"}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            db.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, int(match.group(1))))
            db.commit()
            row = db.execute("SELECT * FROM appointments WHERE id = ?", (int(match.group(1)),)).fetchone()
        if not row:
            self.send_json({"error": "Randevu bulunamadi"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(row_to_dict(row))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        address_match = re.fullmatch(r"/api/profile/addresses/(\d+)", parsed.path)
        if address_match:
            self.delete_address(int(address_match.group(1)))
            return
        pet_match = re.fullmatch(r"/api/profile/pets/(\d+)", parsed.path)
        if pet_match:
            self.delete_pet(int(pet_match.group(1)))
            return
        if not self.require_admin():
            return
        user_match = re.fullmatch(r"/api/admin/users/(\d+)", parsed.path)
        if user_match:
            self.delete_admin_user(int(user_match.group(1)))
            return
        self.send_json({"error": "Endpoint bulunamadi"}, HTTPStatus.NOT_FOUND)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def get_bearer_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth.removeprefix("Bearer ").strip()
        return ""

    def get_session_user(self) -> sqlite3.Row | None:
        token = self.get_bearer_token()
        if not token:
            return None
        with connect() as db:
            return db.execute(
                """
                SELECT users.id, users.google_id, users.full_name, users.name, users.email, users.phone,
                       users.profile_picture, users.role, users.created_at, users.is_banned
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

    def require_admin(self) -> bool:
        payload = decode_admin_jwt(self.get_bearer_token())
        if payload:
            return True
        user = self.get_session_user()
        if not user or user["role"] != "admin":
            self.send_json({"error": "Admin girişi gerekli"}, HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def require_user(self) -> sqlite3.Row | None:
        user = self.get_session_user()
        if not user:
            self.send_json({"error": "Üye girişi gerekli"}, HTTPStatus.UNAUTHORIZED)
            return None
        if user["is_banned"]:
            self.send_json({"error": "Hesabiniz pasif hale getirildi."}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api_get(self, parsed) -> None:
        """GET istekleri: ürünler, profil, admin listeleri ve istatistikler."""
        if parsed.path == "/api/products":
            query = parse_qs(parsed.query)
            category = query.get("category", [None])[0]
            sql = "SELECT * FROM products WHERE active = 1"
            params: list[str] = []
            if category:
                sql += " AND category = ?"
                params.append(category)
            with connect() as db:
                rows = db.execute(sql, params).fetchall()
            self.send_json([row_to_dict(row) for row in rows])
            return

        if parsed.path == "/api/appointments":
            if not self.require_admin():
                return
            with connect() as db:
                rows = db.execute("SELECT * FROM appointments ORDER BY created_at DESC").fetchall()
            self.send_json([row_to_dict(row) for row in rows])
            return

        if parsed.path == "/api/orders":
            if not self.require_admin():
                return
            with connect() as db:
                rows = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
            self.send_json([row_to_dict(row) for row in rows])
            return

        if parsed.path == "/api/stats":
            if not self.require_admin():
                return
            with connect() as db:
                stats = {
                    "total_appointments": first_column(db.execute("SELECT COUNT(*) FROM appointments").fetchone()),
                    "pending_appointments": first_column(db.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'").fetchone()),
                    "total_orders": first_column(db.execute("SELECT COUNT(*) FROM orders").fetchone()),
                    "total_revenue": first_column(db.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()),
                    "total_products": first_column(db.execute("SELECT COUNT(*) FROM products WHERE active = 1").fetchone()),
                    "low_stock_products": first_column(db.execute("SELECT COUNT(*) FROM products WHERE stock < 10 AND active = 1").fetchone()),
                    "total_users": first_column(db.execute("SELECT COUNT(*) FROM users").fetchone()),
                    "active_users": first_column(db.execute("SELECT COUNT(DISTINCT user_id) FROM sessions").fetchone()),
                    "banned_users": first_column(db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()),
                }
            self.send_json(stats)
            return

        if parsed.path == "/api/admin/users":
            if not self.require_admin():
                return
            query = parse_qs(parsed.query)
            search = (query.get("q", [""])[0] or "").strip().lower()
            role = (query.get("role", [""])[0] or "").strip()
            sql = "SELECT id, full_name, email, phone, role, is_banned, created_at FROM users WHERE 1=1"
            params: list[str] = []
            if search:
                sql += " AND (LOWER(full_name) LIKE ? OR LOWER(email) LIKE ? OR phone LIKE ?)"
                like = f"%{search}%"
                params.extend([like, like, like])
            if role in {"member", "admin"}:
                sql += " AND role = ?"
                params.append(role)
            sql += " ORDER BY created_at DESC"
            with connect() as db:
                rows = db.execute(sql, params).fetchall()
            self.send_json([row_to_dict(row) for row in rows])
            return

        if parsed.path == "/api/me":
            user = self.get_session_user()
            self.send_json(row_to_dict(user) if user else {})
            return

        if parsed.path == "/api/profile":
            user = self.require_user()
            if not user:
                return
            with connect() as db:
                addresses = db.execute(
                    "SELECT id, title, address, city, district, created_at FROM user_addresses WHERE user_id = ? ORDER BY id DESC",
                    (user["id"],),
                ).fetchall()
                pets = db.execute(
                    "SELECT id, name, species, age, notes, created_at FROM pets WHERE user_id = ? ORDER BY id DESC",
                    (user["id"],),
                ).fetchall()
                pet_payload = []
                for pet in pets:
                    item = row_to_dict(pet)
                    records = db.execute(
                        """
                        SELECT id, record_type, title, details, record_date, created_at
                        FROM pet_health_records
                        WHERE pet_id = ? AND user_id = ?
                        ORDER BY record_date DESC, id DESC
                        """,
                        (pet["id"], user["id"]),
                    ).fetchall()
                    item["health_records"] = [row_to_dict(record) for record in records]
                    pet_payload.append(item)
                # Eski kayıtlarda user_id yoksa tekil e-posta üzerinden bir kez
                # hesaba bağla. Telefon veya ad benzerliği üzerinden eşleştirme
                # yapılmaz; böylece aynı isimli üyelerin randevuları karışmaz.
                db.execute(
                    """
                    UPDATE appointments
                    SET user_id = ?
                    WHERE user_id IS NULL AND LOWER(email) = LOWER(?)
                    """,
                    (user["id"], user["email"]),
                )
                db.commit()
                appointments = db.execute(
                    """
                    SELECT id, pet_id, pet_name, pet_type, service, appt_date, appt_time, notes, status, created_at
                    FROM appointments
                    WHERE user_id = ?
                    ORDER BY appt_date DESC, appt_time DESC
                    """,
                    (user["id"],),
                ).fetchall()
                reviews = db.execute(
                    """
                    SELECT id, author, pet_type, product_name, rating, message, reply, active, created_at
                    FROM site_reviews
                    WHERE user_id = ?
                    ORDER BY id DESC
                    """,
                    (user["id"],),
                ).fetchall()
                order_rows = db.execute(
                    "SELECT id FROM orders WHERE user_id = ? ORDER BY created_at DESC",
                    (user["id"],),
                ).fetchall()
                orders = [order_with_items(db, row["id"]) for row in order_rows]
            self.send_json(
                {
                    "user": row_to_dict(user),
                    "addresses": [row_to_dict(row) for row in addresses],
                    "pets": pet_payload,
                    "appointments": [row_to_dict(row) for row in appointments],
                    "reviews": [row_to_dict(row) for row in reviews],
                    "orders": [order for order in orders if order],
                }
            )
            return

        self.send_json({"error": "Endpoint bulunamadi"}, HTTPStatus.NOT_FOUND)

    def create_appointment(self) -> None:
        """Online randevu formunu kaydeder ve hatırlatma kayıtlarını oluşturur."""
        try:
            user = self.get_session_user()
            data = validate_appointment(apply_member_appointment_defaults(self.read_json(), user))
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        now = datetime.now().isoformat(timespec="seconds")
        with connect() as db:
            # Dolu bir saat seçildiyse yeni hayvan kaydı oluşturmadan işlemi durdur.
            if not is_appointment_time_available(db, data["appt_date"], data["appt_time"]):
                self.send_json({"error": "Bu randevu saati dolu veya kapalı. Lutfen baska bir saat secin."}, HTTPStatus.CONFLICT)
                return
            selected_pet_id = None
            if user and data.get("pet_id"):
                selected_pet = db.execute(
                    "SELECT id FROM pets WHERE id = ? AND user_id = ?",
                    (int(data["pet_id"]), user["id"]),
                ).fetchone()
                if not selected_pet:
                    self.send_json({"error": "Seçilen hayvan kaydı bulunamadı."}, HTTPStatus.BAD_REQUEST)
                    return
                selected_pet_id = selected_pet["id"]
            if user and data.get("save_pet"):
                pet_name = (data.get("pet_name") or "").strip()
                pet_species = (data.get("pet_type") or "").strip()
                if pet_name and pet_species and pet_species != "Belirtilmedi":
                    existing_pet = db.execute(
                        "SELECT id FROM pets WHERE user_id = ? AND LOWER(name) = LOWER(?) AND LOWER(species) = LOWER(?)",
                        (user["id"], pet_name, pet_species),
                    ).fetchone()
                    if existing_pet:
                        selected_pet_id = existing_pet["id"]
                    else:
                        selected_pet_id = db.execute(
                            """
                            INSERT INTO pets (user_id, name, species, age, notes, created_at)
                            VALUES (?, ?, ?, '', 'Randevu ekranından eklendi', ?)
                            """,
                            (user["id"], pet_name, pet_species, now),
                        ).lastrowid
            try:
                cursor = db.execute(
                    """
                    INSERT INTO appointments
                    (user_id, pet_id, first_name, last_name, phone, email, pet_type, pet_name, service, appt_date, appt_time, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"] if user else None,
                        selected_pet_id,
                        data["first_name"].strip(),
                        data["last_name"].strip(),
                        data["phone"],
                        data.get("email", "").strip(),
                        data["pet_type"].strip(),
                        data.get("pet_name", "").strip(),
                        data["service"].strip(),
                        data["appt_date"],
                        data["appt_time"],
                        data.get("notes", "").strip(),
                        now,
                    ),
                )
            except Exception as exc:
                if "DUPLICATE_APPOINTMENT_SLOT" in str(exc) or (
                    DATABASE_URL and "idx_appointments_active_slot" in str(exc)
                ):
                    self.send_json({"error": "Bu randevu saati dolu. Lutfen baska bir saat secin."}, HTTPStatus.CONFLICT)
                    return
                raise
            appointment_id = cursor.lastrowid
            self.create_reminder_rows(db, appointment_id, data)
            db.commit()
            row = db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        self.send_json(row_to_dict(row), HTTPStatus.CREATED)

    def create_purchase_review(self) -> None:
        """Sadece daha önce sipariş oluşturan üyelerin yorum eklemesini sağlar."""
        user = self.require_user()
        if not user:
            return
        try:
            data = self.read_json()
            rating = int(data.get("rating") or 5)
        except (json.JSONDecodeError, ValueError):
            self.send_json({"error": "Geçersiz yorum verisi"}, HTTPStatus.BAD_REQUEST)
            return
        message = (data.get("message") or "").strip()
        pet_type = (data.get("pet_type") or "Hasta Sahibi").strip()
        product_name = (data.get("product_name") or "Genel").strip()
        if rating < 1 or rating > 5:
            self.send_json({"error": "Puan 1 ile 5 arasinda olmalı"}, HTTPStatus.BAD_REQUEST)
            return
        if len(message) < 8:
            self.send_json({"error": "Yorum en az 8 karakter olmalı"}, HTTPStatus.BAD_REQUEST)
            return
        if len(message) > 500:
            self.send_json({"error": "Yorum en fazla 500 karakter olabilir"}, HTTPStatus.BAD_REQUEST)
            return
        with connect() as db:
            purchased = first_column(db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user["id"],)).fetchone())
            if purchased < 1:
                self.send_json({"error": "Yorum yapabilmek için önce satın alma yapmış olmalısiniz."}, HTTPStatus.FORBIDDEN)
                return
            cursor = db.execute(
                """
                INSERT INTO site_reviews (author, pet_type, product_name, rating, message, reply, active, created_at)
                VALUES (?, ?, ?, ?, ?, '', 1, ?)
                """,
                (user["full_name"], pet_type, product_name, rating, message, datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
            row = db.execute("SELECT * FROM site_reviews WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.send_json(row_to_dict(row), HTTPStatus.CREATED)

    def create_reminder_rows(self, db: sqlite3.Connection, appointment_id: int, data: dict) -> None:
        """Randevu yaklasinca gonderilecek SMS/e-posta hatırlatma kayitlari."""
        try:
            appt_at = datetime.strptime(f"{data['appt_date']} {data['appt_time']}", "%Y-%m-%d %H:%M")
        except ValueError:
            return
        now = datetime.now().isoformat(timespec="seconds")
        moments = [appt_at - timedelta(days=1), appt_at - timedelta(hours=2)]
        recipients = [("sms", data.get("phone", "")), ("email", (data.get("email") or "").strip())]
        for scheduled_at in moments:
            if scheduled_at <= datetime.now():
                continue
            for channel, recipient in recipients:
                if not recipient:
                    continue
                db.execute(
                    """
                    INSERT INTO appointment_reminders
                    (appointment_id, channel, recipient, scheduled_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (appointment_id, channel, recipient, scheduled_at.isoformat(timespec="seconds"), now),
                )

    def create_order(self) -> None:
        """Sepetteki ürünleri siparişe çevirir, stoktan düşer ve demo ödeme bilgisini saklar."""
        try:
            data = self.read_json()
            user = self.get_session_user()
            items = data.get("items") or []
            if not items:
                raise ValueError("Sepet boş")
            card_number = re.sub(r"\D+", "", data.get("card_number", ""))
            card_name = (data.get("card_name") or "").strip()
            card_expiry = (data.get("card_expiry") or "").strip()
            card_cvc = re.sub(r"\D+", "", data.get("card_cvc", ""))
            if not card_name or not re.fullmatch(r"\d{12,19}", card_number):
                raise ValueError("Gecerli kart bilgisi girin")
            if not re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*\d{2}", card_expiry):
                raise ValueError("Son kullanma tarihi AA/YY formatında olmalı")
            if not re.fullmatch(r"\d{3,4}", card_cvc):
                raise ValueError("Gecerli CVC girin")
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            address = (data.get("address") or "").strip()
            if user and data.get("address_id"):
                address_row = db.execute(
                    "SELECT address FROM user_addresses WHERE id = ? AND user_id = ?",
                    (int(data["address_id"]), user["id"]),
                ).fetchone()
                if not address_row:
                    self.send_json({"error": "Adres bulunamadi"}, HTTPStatus.NOT_FOUND)
                    return
                address = address_row["address"]
            if len(address) < 10:
                self.send_json({"error": "Lutfen tam adres girin"}, HTTPStatus.BAD_REQUEST)
                return

            if user:
                name_parts = (user["full_name"] or "").strip().split(" ", 1)
                first_name = name_parts[0] if name_parts else ""
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                phone_value = (data.get("phone") or "").strip()
                phone = user["phone"] or (validate_phone(phone_value) if phone_value else "")
                email = user["email"]
                user_id = user["id"]
            else:
                if not data.get("first_name") or not data.get("last_name"):
                    self.send_json({"error": "Ad ve soyad zorunlu"}, HTTPStatus.BAD_REQUEST)
                    return
                first_name = data["first_name"].strip()
                last_name = data["last_name"].strip()
                phone = validate_phone(data.get("phone", ""))
                email = data.get("email", "").strip()
                user_id = None

            total = 0.0
            product_rows = []
            for item in items:
                product_id = int(item["product_id"])
                quantity = int(item["quantity"])
                if quantity < 1:
                    self.send_json({"error": "Miktar en az 1 olmalı"}, HTTPStatus.BAD_REQUEST)
                    return
                product = db.execute("SELECT * FROM products WHERE id = ? AND active = 1", (product_id,)).fetchone()
                if not product:
                    self.send_json({"error": f"Urun bulunamadi: {product_id}"}, HTTPStatus.NOT_FOUND)
                    return
                if product["stock"] < quantity:
                    self.send_json({"error": f"{product['name']} için yeterli stok yok"}, HTTPStatus.BAD_REQUEST)
                    return
                total += product["price"] * quantity
                product_rows.append((product, quantity))

            cursor = db.execute(
                """
                INSERT INTO orders
                (user_id, first_name, last_name, phone, email, address, notes, total, payment_last4, payment_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    first_name,
                    last_name,
                    phone,
                    email,
                    address,
                    data.get("notes", "").strip(),
                    round(total, 2),
                    card_number[-4:],
                    "demo_paid",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            order_id = cursor.lastrowid
            for product, quantity in product_rows:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (order_id, product["id"], quantity, product["price"]),
                )
                db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product["id"]))
            db.commit()
            order = row_to_dict(db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
            order["items"] = [
                row_to_dict(row)
                for row in db.execute(
                    """
                    SELECT product_id, quantity, unit_price
                    FROM order_items
                    WHERE order_id = ?
                    """,
                    (order_id,),
                ).fetchall()
            ]
        self.send_json(order, HTTPStatus.CREATED)

    def create_address(self) -> None:
        """Üyenin profilindeki teslimat adresini veritabanına ekler."""
        user = self.require_user()
        if not user:
            return
        try:
            data = self.read_json()
            title = (data.get("title") or "Adres").strip()
            address = (data.get("address") or "").strip()
            city = (data.get("city") or "").strip()
            district = (data.get("district") or "").strip()
            if not title:
                title = "Adres"
            if len(address) < 10:
                raise ValueError("Lutfen tam adres girin")
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            cursor = db.execute(
                """
                INSERT INTO user_addresses (user_id, title, address, city, district, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], title, address, city, district, datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
            row = db.execute("SELECT id, title, address, city, district, created_at FROM user_addresses WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.send_json(row_to_dict(row), HTTPStatus.CREATED)

    def create_pet(self) -> None:
        """Üyenin profilindeki hayvan kaydıni veritabanına ekler."""
        user = self.require_user()
        if not user:
            return
        try:
            data = self.read_json()
            name = (data.get("name") or "").strip()
            species = (data.get("species") or "").strip()
            age = (data.get("age") or "").strip()
            notes = (data.get("notes") or "").strip()
            if not name or not species:
                raise ValueError("Hayvan adi ve turu zorunlu")
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            cursor = db.execute(
                """
                INSERT INTO pets (user_id, name, species, age, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], name, species, age, notes, datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
            row = db.execute("SELECT id, name, species, age, notes, created_at FROM pets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.send_json(row_to_dict(row), HTTPStatus.CREATED)

    def delete_address(self, address_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        with connect() as db:
            cursor = db.execute("DELETE FROM user_addresses WHERE id = ? AND user_id = ?", (address_id, user["id"]))
            db.commit()
        if cursor.rowcount < 1:
            self.send_json({"error": "Adres bulunamadi"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json({"message": "Adres silindi"})

    def delete_pet(self, pet_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        with connect() as db:
            db.execute("DELETE FROM pet_health_records WHERE pet_id = ? AND user_id = ?", (pet_id, user["id"]))
            cursor = db.execute("DELETE FROM pets WHERE id = ? AND user_id = ?", (pet_id, user["id"]))
            db.commit()
        if cursor.rowcount < 1:
            self.send_json({"error": "Hayvan bulunamadi"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json({"message": "Hayvan silindi"})

    def create_contact(self) -> None:
        try:
            data = self.read_json()
            if not data.get("full_name") or not data.get("email"):
                raise ValueError("Ad soyad ve email zorunlu")
            if len((data.get("message") or "").strip()) < 10:
                raise ValueError("Mesaj en az 10 karakter olmalı")
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            db.execute(
                "INSERT INTO contacts (full_name, email, subject, message, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    data["full_name"].strip(),
                    data["email"].strip(),
                    data.get("subject", "").strip(),
                    data["message"].strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            db.commit()
        self.send_json({"message": "Mesajiniz iletildi."}, HTTPStatus.CREATED)

    def create_user(self) -> None:
        """Yeni üye kaydı oluşturur; telefon ve şifre kontrollerini yapar."""
        try:
            data = self.read_json()
            full_name = (data.get("full_name") or "").strip()
            email = validate_email(data.get("email", ""))
            phone = validate_phone(data.get("phone", ""))
            if not full_name:
                raise ValueError("Ad soyad zorunlu")
            password_hash, password_salt = hash_password(data.get("password", ""))
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        try:
            with connect() as db:
                existing = db.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)",
                    (email,),
                ).fetchone()
                if existing:
                    self.send_json({"error": "Bu email ile kayıtlı bir üye zaten var"}, HTTPStatus.CONFLICT)
                    return
                existing_phone = db.execute(
                    "SELECT id FROM users WHERE phone = ?",
                    (phone,),
                ).fetchone()
                if existing_phone:
                    self.send_json({"error": "Bu telefon numarası ile kayıtlı bir üye zaten var"}, HTTPStatus.CONFLICT)
                    return
                cursor = db.execute(
                    """
                    INSERT INTO users (full_name, email, phone, password_hash, password_salt, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        full_name,
                        email,
                        phone,
                        password_hash,
                        password_salt,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                user = db.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
                token = create_user_session(db, user, remember=True)
                db.commit()
        except Exception as exc:
            if "unique" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                raise
            self.send_json({"error": "Bu email veya telefon ile kayıtlı bir üye zaten var"}, HTTPStatus.CONFLICT)
            return

        self.send_json(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "name": user["name"] if "name" in user.keys() else user["full_name"],
                    "email": user["email"],
                    "phone": user["phone"],
                    "profile_picture": user["profile_picture"] if "profile_picture" in user.keys() else "",
                    "role": user["role"],
                    "is_banned": user["is_banned"],
                    "created_at": user["created_at"],
                },
            },
            HTTPStatus.CREATED,
        )

    def login_user(self, required_role: str) -> None:
        """Normal üye veya admin girişini kontrol eder ve session token üretir."""
        try:
            data = self.read_json()
            email = validate_email(data.get("email", ""))
            password = data.get("password", "")
            remember = bool(data.get("remember", False))
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with connect() as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if (
                not user
                or not verify_password(password, user["password_hash"], user["password_salt"])
                or user["role"] != required_role
                or user["is_banned"]
            ):
                message = "Bu panel yalnızca yöneticiler içindir." if user and user["role"] != required_role and required_role == "admin" else "Email veya şifre hatalı"
                if user and user["is_banned"]:
                    message = "Hesabiniz pasif hale getirildi."
                self.send_json({"error": message}, HTTPStatus.UNAUTHORIZED)
                return

            # Klasik giriş de Google girişiyle aynı session üreticisini kullanır.
            # Böylece "Beni hatırla" seçimi Flask cookie'sine de uygulanır.
            token = create_user_session(db, user, remember=remember)
            db.commit()

        self.send_json(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "name": user["name"] if "name" in user.keys() else user["full_name"],
                    "email": user["email"],
                    "phone": user["phone"],
                    "profile_picture": user["profile_picture"] if "profile_picture" in user.keys() else "",
                    "role": user["role"],
                    "is_banned": user["is_banned"],
                    "created_at": user["created_at"],
                },
            }
        )

    def logout_user(self) -> None:
        token = self.get_bearer_token()
        if token:
            with connect() as db:
                db.execute("DELETE FROM sessions WHERE token = ?", (token,))
                db.commit()
        self.send_json({"message": "Çıkış yapildi"})

    def update_admin_user(self, user_id: int) -> None:
        try:
            data = self.read_json()
        except json.JSONDecodeError:
            self.send_json({"error": "Geçersiz JSON"}, HTTPStatus.BAD_REQUEST)
            return

        updates = []
        params = []
        if "role" in data:
            if data["role"] not in {"member", "admin"}:
                self.send_json({"error": "Geçersiz rol"}, HTTPStatus.BAD_REQUEST)
                return
            updates.append("role = ?")
            params.append(data["role"])
        if "is_banned" in data:
            updates.append("is_banned = ?")
            params.append(1 if data["is_banned"] else 0)
        if not updates:
            self.send_json({"error": "Guncellenecek alan yok"}, HTTPStatus.BAD_REQUEST)
            return

        params.append(user_id)
        with connect() as db:
            db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            db.execute("DELETE FROM sessions WHERE user_id = ? AND ? = 1", (user_id, 1 if data.get("is_banned") else 0))
            db.commit()
            user = db.execute(
                "SELECT id, full_name, email, phone, role, is_banned, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not user:
            self.send_json({"error": "Kullanıcı bulunamadi"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(row_to_dict(user))

    def delete_admin_user(self, user_id: int) -> None:
        with connect() as db:
            user = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                self.send_json({"error": "Kullanıcı bulunamadi"}, HTTPStatus.NOT_FOUND)
                return
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM user_addresses WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
        self.send_json({"message": "Kullanıcı silindi"})


class FlaskGumusVeterinerAdapter(GumusVeterinerHandler):
    """Flask request'lerini eski handler metotlarına bağlayan küçük adaptör."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.headers = request.headers
        self._response: Response | None = None

    def read_json(self) -> dict:
        return request.get_json(silent=True) or {}

    def send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        self._response = Response(body, status=int(status), content_type="application/json; charset=utf-8")

    def flask_response(self) -> Response:
        return self._response or Response(
            json.dumps({"error": "Yanıt oluşturulamadı"}, ensure_ascii=False),
            status=int(HTTPStatus.INTERNAL_SERVER_ERROR),
            content_type="application/json; charset=utf-8",
        )


@app.before_request
def ensure_database_ready():
    # Railway'de container ilk açıldığında data klasörü yoksa otomatik oluşturulur.
    if request.path == "/health":
        return
    ensure_database_initialized()
    if csrf_required_for_request():
        sent_token = request.headers.get("X-CSRF-Token", "")
        if not sent_token or not hmac.compare_digest(sent_token, session.get("csrf_token", "")):
            return api_response(False, "CSRF doğrulaması başarısız", None, HTTPStatus.FORBIDDEN)


@app.after_request
def add_security_headers(response: Response) -> Response:
    # Yalnızca izin verilen web origin'lerine CORS cevabı eklenir.
    request_origin = request.headers.get("Origin", "")
    if request_origin in ALLOWED_CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://wwwgumusvet.com https://gumusveteriner.onrender.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/static/") or request.path.lower().endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico")):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.path in {"/", "/admin", "/admin/login"}:
        response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        "csrf_token",
        get_csrf_token(),
        secure=True,
        httponly=False,
        samesite="Lax",
        max_age=60 * 60 * 24,
    )
    return response


# ---------------------------------------------------------------------------
# Flask route'ları
# ---------------------------------------------------------------------------
# Bu bölüm canlı ortamda gelen HTTP isteklerini karşılar. Web sitesi HTML'i,
# SEO dosyaları, public API'ler ve admin API'leri burada tanımlanır.
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Canlı ortamda traceback gostermeden güvenli API hata cevabi doner."""
    if isinstance(error, RateLimitExceeded):
        body, status = api_response(False, "Çok fazla istek gönderildi. Lütfen biraz bekleyin.", None, HTTPStatus.TOO_MANY_REQUESTS)
        return body, status
    if isinstance(error, HTTPException):
        if request.path.startswith("/api/"):
            body, status = api_response(False, error.description or "İstek işlenemedi.", None, HTTPStatus(error.code or 500))
            return body, status
        return error
    if request.path.startswith("/api/"):
        security_logger.exception("unhandled_api_error path=%s", request.path)
        body, status = api_response(False, "Sunucu hatası. Lütfen tekrar deneyin.", None, HTTPStatus.INTERNAL_SERVER_ERROR)
        return body, status
    security_logger.exception("unhandled_page_error path=%s", request.path)
    return Response(
        "Beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
        status=int(HTTPStatus.INTERNAL_SERVER_ERROR),
        content_type="text/plain; charset=utf-8",
    )


@app.route("/")
@app.route("/hizmetler")
@app.route("/urunler")
@app.route("/iletisim")
@app.route("/admin")
@app.route("/admin/login")
@app.route("/403")
def serve_app_index() -> str:
    # Tüm tek sayfa uygulama route'ları aynı index.html dosyasını kullanır.
    return render_template("index.html", asset_version=DEPLOY_VERSION, csrf_token=get_csrf_token())


@app.route("/ürünler")
def redirect_legacy_products_url():
    """Türkçe karakterli eski ürün URL'sini arama motorları için kalıcı yönlendirir."""
    return redirect("/urunler", code=HTTPStatus.MOVED_PERMANENTLY)


@app.route("/iletişim")
def redirect_legacy_contact_url():
    """Türkçe karakterli eski iletişim URL'sini arama motorları için kalıcı yönlendirir."""
    return redirect("/iletisim", code=HTTPStatus.MOVED_PERMANENTLY)


@app.route("/login")
@limiter.limit("5 per minute")
def login_page():
    """SPA içindeki kullanıcı giriş ekranına yönlendirir."""
    return redirect("/#login")


@app.route("/health")
def health() -> tuple[str, int]:
    # Railway health check bu endpointten hızlı cevap alır.
    return "OK", 200


@app.route("/api/health")
def api_health():
    database_type = "postgres" if DATABASE_URL else "sqlite"
    sqlite_storage = None
    if not DATABASE_URL:
        sqlite_storage = (
            "persistent-disk"
            if os.environ.get("SQLITE_DB_PATH") and DB_PATH != DEFAULT_DB_PATH
            else "ephemeral-local"
        )
    mail_status = get_mail_status()
    return api_response(
        True,
        "API çalışıyor",
        {
            "service": "gumus-veteriner",
            "database_pool": "sqlalchemy-ready",
            "database_type": database_type,
            "runtime_database": database_type,
            "configured_database": database_type,
            "sqlite_storage": sqlite_storage,
            "mail_provider": get_mail_provider(),
            "mail_configured": mail_is_configured(),
            "mail_sender": mail_status["sender"],
            "mail_smtp_host": mail_status["host"],
            "mail_smtp_port": mail_status["port"],
            "mail_smtp_tls": mail_status["tls"],
            "mail_sender_matches_login": mail_status["sender_matches_login"],
            "mail_app_password_format_valid": mail_status[
                "app_password_format_valid"
            ],
            "gmail_api_fallback_configured": mail_status[
                "gmail_api_fallback_configured"
            ],
        },
    )


@app.route("/api/csrf-token")
def api_csrf_token():
    return api_response(True, "CSRF token hazır", {"csrf_token": get_csrf_token()})


@app.route("/api/deploy-info")
def api_deploy_info():
    """Render/GitHub deployunun hangi sürümü çalıştırdığını test etmek için."""
    data = {
        "version": DEPLOY_VERSION,
        "service": os.environ.get("RENDER_SERVICE_NAME", ""),
        "branch": os.environ.get("RENDER_GIT_BRANCH", "main"),
        "environment": "render" if os.environ.get("RENDER") else "local",
        "features": [
            "appointment_slots",
            "purchase_reviews",
            "admin_sms",
            "admin_apis",
            "member_pet_select",
        ],
    }
    return api_response(True, "Deploy bilgisi", data)


@app.route("/robots.txt")
def robots_txt() -> Response:
    """Arama motorlarına tarama izni ve sitemap adresini bildirir."""
    content = f"""User-agent: *
Allow: /
Allow: /static/logo.jpeg

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content, content_type="text/plain; charset=utf-8")


@app.route("/sitemap.xml")
def sitemap_xml() -> Response:
    """Google ve diğer arama motorları için temel site haritası üretir."""
    today = date.today().isoformat()
    urls = [
        (SITE_URL, "1.0", "weekly"),
        (f"{SITE_URL}/hizmetler", "0.8", "weekly"),
        (f"{SITE_URL}/urunler", "0.8", "weekly"),
        (f"{SITE_URL}/iletisim", "0.7", "monthly"),
    ]
    url_nodes = []
    for loc, priority, changefreq in urls:
        logo_image = (
            f"""
    <image:image>
      <image:loc>{SITE_URL}/static/logo.jpeg</image:loc>
      <image:title>Gümüş Veteriner logosu</image:title>
    </image:image>"""
            if loc == SITE_URL
            else ""
        )
        url_nodes.append(
            f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
{logo_image}
  </url>"""
        )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
{chr(10).join(url_nodes)}
</urlset>
"""
    return Response(content, content_type="application/xml; charset=utf-8")


@app.route("/login/google")
@limiter.limit("10 per hour")
def google_login():
    """Google OAuth akışıni baslatir."""
    google = ensure_google_oauth()
    if not google:
        return redirect("/?google_error=missing_config")
    remember = request.args.get("remember") == "1"
    session["google_remember"] = remember
    redirect_uri = (
        os.environ.get("GOOGLE_REDIRECT_URI")
        or (f"{SITE_URL}/login/google/authorized" if IS_PRODUCTION else url_for("google_authorized", _external=True))
    )
    return google.authorize_redirect(redirect_uri)


@app.route("/login/google/authorized")
@app.route("/auth/google/callback")
def google_authorized():
    """Google'dan donen kullanıcıyi users tablosuna kaydeder veya eslestirir."""
    google = ensure_google_oauth()
    if not google:
        return redirect("/?google_error=missing_config")
    try:
        token = google.authorize_access_token()
        profile = token.get("userinfo")
        if not profile:
            profile = google.get("userinfo").json()
        remember = bool(session.pop("google_remember", False))
        with connect() as db:
            user = UserModel.upsert_google_user(db, dict(profile))
            session_token = create_user_session(db, user, remember=remember)
            db.commit()
        session["google_login_token"] = session_token
        return redirect("/?google_login=success")
    except Exception:
        security_logger.exception("google_oauth_failed")
        return redirect("/?google_error=oauth_failed")


@app.route("/logout")
def logout_page():
    """Google veya normal üye oturumunu kapatip ana sayfaya dondurur."""
    token = session.get("session_token", "")
    if token:
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            db.commit()
    session.clear()
    return redirect("/")


@app.route("/api/session", methods=["GET"])
def api_session_user():
    """Flask session cookie'sinden aktif kullanıcıyi frontend'e verir."""
    token = session.get("session_token") or session.pop("google_login_token", "")
    if not token:
        return api_response(False, "Aktif oturum yok", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        row = db.execute(
            """
            SELECT users.id, users.google_id, users.full_name, users.name, users.email, users.phone,
                   users.profile_picture, users.role, users.created_at, users.is_banned
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
    if not row or row["is_banned"]:
        session.clear()
        return api_response(False, "Aktif oturum yok", None, HTTPStatus.UNAUTHORIZED)
    return api_response(True, "Oturum aktif", {"token": token, "user": row_to_dict(row)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Hem bearer token'ı hem Flask session cookie'sini kapatir."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    token = token or session.get("session_token", "")
    if token:
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            db.commit()
    # Çıkıştan sonra sayfa yenilenmeden yeniden giriş yapılabilmesi için
    # tarayıcı formunun mevcut CSRF tokenını koruyoruz.
    csrf_token = session.get("csrf_token")
    session.clear()
    if csrf_token:
        session["csrf_token"] = csrf_token
    return api_response(True, "Çıkış yapıldı", {})


@app.route("/api/test-mail", methods=["POST"])
@limiter.limit("5 per hour")
def api_test_mail():
    """SMTP ayarlarını yalnızca admin veya açık test modu ile doğrular."""
    debug_mail_test = env_flag("DEBUG_MAIL_TEST", default=False)
    if not debug_mail_test:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if not decode_admin_jwt(token):
            return api_response(False, "Admin yetkisi gerekli", None, HTTPStatus.UNAUTHORIZED)

    data = request.get_json(silent=True) or {}
    recipient = (
        data.get("email")
        or os.environ.get("SMTP_TEST_RECIPIENT")
        or os.environ.get("SMTP_USERNAME")
        or ""
    )
    try:
        recipient = validate_email(recipient)
    except ValueError:
        return api_response(False, "Test alıcısı için geçerli bir e-posta girin", None, HTTPStatus.BAD_REQUEST)

    mail_result = send_email(
        recipient,
        "Gümüş Veteriner SMTP test maili",
        "Bu mesaj Gümüş Veteriner mail ayarlarının çalıştığını doğrulamak için gönderildi.",
    )
    if not mail_result.success:
        security_logger.error(
            "smtp_test_mail_failed email=%s detail=%s",
            recipient,
            mail_result.detail or mail_result.message,
        )
        return api_response(
            False,
            "Test maili gönderilemedi",
            {"detail": mail_result.detail or mail_result.message},
            HTTPStatus.BAD_GATEWAY,
        )
    security_logger.info("smtp_test_mail_sent email=%s", recipient)
    return api_response(True, "Test maili gönderildi", {"email": recipient})


@app.route("/api/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
def api_forgot_password():
    """Kullanıcı hesabını açıklamadan 30 dakikalık tek kullanımlık bağlantı gönderir."""
    generic_message = (
        "Bu e-posta kayıtlıysa şifre sıfırlama bağlantısı gönderildi."
    )
    data = request.get_json(silent=True) or {}
    try:
        email = validate_email(data.get("email", ""))
    except ValueError:
        # Kullanıcı var/yok bilgisini ve e-posta doğrulama ayrıntısını dışarı sızdırmayız.
        security_logger.info(
            "password_reset_requested invalid_email ip=%s",
            request.remote_addr or "",
        )
        return api_response(True, generic_message, {})

    with connect() as db:
        user = db.execute(
            "SELECT id, full_name, email FROM users WHERE LOWER(email) = LOWER(?)",
            (email,),
        ).fetchone()
        if not user:
            security_logger.info(
                "password_reset_requested unknown_email=%s ip=%s",
                email,
                request.remote_addr or "",
            )
            return api_response(True, generic_message, {})

        raw_token = secrets.token_urlsafe(48)
        token_hash = hash_reset_token(raw_token)
        now = datetime.now()
        expires_at = now + timedelta(minutes=30)
        db.execute(
            """
            UPDATE password_resets
            SET used_at = ?
            WHERE user_id = ? AND used_at IS NULL
            """,
            (now.isoformat(timespec="seconds"), user["id"]),
        )
        db.execute(
            """
            INSERT INTO password_resets
            (token, user_id, expires_at, used_at, created_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (
                token_hash,
                user["id"],
                expires_at.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"),
            ),
        )
        db.commit()

    reset_url = f"{SITE_URL}/?reset_token={raw_token}"
    body = (
        f"Merhaba {user['full_name'] or ''},\n\n"
        "Gümüş Veteriner hesabınız için şifre sıfırlama talebi aldık.\n"
        "Aşağıdaki bağlantı 30 dakika boyunca ve yalnızca bir kez kullanılabilir:\n\n"
        f"{reset_url}\n\n"
        "Bu talebi siz yapmadıysanız bu e-postayı dikkate almayın.\n\n"
        "Gümüş Veteriner Muayenehanesi\n"
        "0546 136 14 33"
    )
    mail_result = send_email(
        user["email"],
        "Gümüş Veteriner şifre sıfırlama bağlantısı",
        body,
    )
    if mail_result.success:
        security_logger.info(
            "password_reset_mail_sent user_id=%s email=%s",
            user["id"],
            email,
        )
    else:
        # Güvenli genel cevap korunur; gerçek SMTP hatası Render loglarında bulunur.
        security_logger.error(
            "password_reset_mail_failed user_id=%s email=%s detail=%s",
            user["id"],
            email,
            mail_result.detail or mail_result.message,
        )
    return api_response(True, generic_message, {})


@app.route("/api/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def api_reset_password():
    """Maildeki token ile kullanıcının yeni şifresini kaydeder."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    if not token:
        return api_response(False, "Sıfırlama bağlantısı geçersiz", None, HTTPStatus.BAD_REQUEST)
    try:
        password_hash, password_salt = hash_password(password)
    except ValueError as exc:
        return api_response(False, str(exc), None, HTTPStatus.BAD_REQUEST)

    now = datetime.now()
    with connect() as db:
        reset = db.execute(
            """
            SELECT password_resets.*, users.email
            FROM password_resets
            JOIN users ON users.id = password_resets.user_id
            WHERE password_resets.token = ?
            """,
            (hash_reset_token(token),),
        ).fetchone()
        if not reset or reset["used_at"] or datetime.fromisoformat(reset["expires_at"]) < now:
            return api_response(False, "Sıfırlama bağlantısı süresi dolmuş veya kullanılmış", None, HTTPStatus.BAD_REQUEST)
        db.execute(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
            (password_hash, password_salt, reset["user_id"]),
        )
        db.execute(
            "UPDATE password_resets SET used_at = ? WHERE token = ?",
            (now.isoformat(timespec="seconds"), hash_reset_token(token)),
        )
        db.execute("DELETE FROM sessions WHERE user_id = ?", (reset["user_id"],))
        db.commit()
    security_logger.info("password_reset_completed user_id=%s ip=%s", reset["user_id"], request.remote_addr or "")
    return api_response(True, "Şifreniz güncellendi. Yeni şifrenizle giriş yapabilirsiniz.", {})


@app.route("/api/site/content", methods=["GET"])
def api_site_content():
    user = get_request_session_user()
    with connect() as db:
        text_rows = db.execute("SELECT text_key, label, value, updated_at FROM site_texts ORDER BY text_key").fetchall()
        review_rows = db.execute("SELECT * FROM site_reviews WHERE active = 1 ORDER BY id DESC").fetchall()
        reviews = []
        for row in review_rows:
            review = row_to_dict(row)
            review["can_delete"] = bool(user and row["user_id"] == user["id"])
            reviews.append(review)
    data = {
        "texts": [row_to_dict(row) for row in text_rows],
        "reviews": reviews,
    }
    return api_response(True, "Site içeriği listelendi", data)


@app.route("/api/appointment-slots", methods=["GET"])
def api_appointment_slots():
    appt_date = (request.args.get("date") or "").strip()
    try:
        datetime.strptime(appt_date, "%Y-%m-%d")
    except ValueError:
        return api_response(False, "Tarih YYYY-MM-DD formatında olmalı", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        rows = appointment_slot_summary(db, appt_date)
    return api_response(True, "Randevu saatleri listelendi", rows)


@app.route("/api/reviews", methods=["POST"])
def api_purchase_review():
    user = get_request_session_user()
    if user and user["is_banned"]:
        return api_response(False, "Hesabınız pasif durumda", None, HTTPStatus.UNAUTHORIZED)
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    pet_type = (data.get("pet_type") or "Hasta Sahibi").strip()
    product_name = (data.get("product_name") or "Genel").strip()
    author = (user["full_name"] if user else data.get("author") or "").strip()
    try:
        rating = int(data.get("rating") or 5)
    except (TypeError, ValueError):
        return api_response(False, "Puan geçersiz", None, HTTPStatus.BAD_REQUEST)
    if rating < 1 or rating > 5:
        return api_response(False, "Puan 1 ile 5 arasında olmalı", None, HTTPStatus.BAD_REQUEST)
    if len(message) < 8:
        return api_response(False, "Yorum en az 8 karakter olmalı", None, HTTPStatus.BAD_REQUEST)
    if len(message) > 500:
        return api_response(False, "Yorum en fazla 500 karakter olabilir", None, HTTPStatus.BAD_REQUEST)
    if len(author) < 2:
        return api_response(False, "Yorum için adınızı yazın", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        if product_name != "Genel":
            if not user:
                return api_response(False, "Ürün yorumu için üye girişi yapmalısınız.", None, HTTPStatus.UNAUTHORIZED)
            purchased = db.execute(
                """
                SELECT COUNT(*)
                FROM orders
                JOIN order_items ON order_items.order_id = orders.id
                JOIN products ON products.id = order_items.product_id
                WHERE orders.user_id = ? AND products.name = ?
                """,
                (user["id"], product_name),
            ).fetchone()
            purchased = first_column(purchased)
            if purchased < 1:
                return api_response(False, "Yalnızca satın aldığınız ürünlere yorum yapabilirsiniz.", None, HTTPStatus.FORBIDDEN)
        cursor = db.execute(
            """
            INSERT INTO site_reviews (user_id, author, pet_type, product_name, rating, message, reply, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, '', 1, ?)
            """,
            (user["id"] if user else None, author, pet_type, product_name, rating, message, datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        row = db.execute("SELECT * FROM site_reviews WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return api_response(True, "Yorumunuz yayınlandı", row_to_dict(row), HTTPStatus.CREATED)


@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def api_member_review_delete(review_id: int):
    """Üye yalnızca kendi hesabıyla oluşturduğu yorumu silebilir."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Yorum silmek için üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        cursor = db.execute(
            "DELETE FROM site_reviews WHERE id = ? AND user_id = ?",
            (review_id, user["id"]),
        )
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Yorum bulunamadı veya bu yorumu silme yetkiniz yok", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Yorumunuz silindi", {})


@app.route("/api/reviews/<int:review_id>", methods=["PATCH", "PUT"])
def api_member_review_update(review_id: int):
    """Üye yalnızca kendi yorumunun metnini, puanını ve hayvan türünü düzenleyebilir."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Yorum düzenlemek için üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    pet_type = (data.get("pet_type") or "Hasta Sahibi").strip()
    try:
        rating = int(data.get("rating") or 5)
    except (TypeError, ValueError):
        return api_response(False, "Puan geçersiz", None, HTTPStatus.BAD_REQUEST)
    if len(message) < 8 or len(message) > 500:
        return api_response(False, "Yorum 8 ile 500 karakter arasında olmalı", None, HTTPStatus.BAD_REQUEST)
    if rating < 1 or rating > 5:
        return api_response(False, "Puan 1 ile 5 arasında olmalı", None, HTTPStatus.BAD_REQUEST)
    if len(pet_type) > 80:
        return api_response(False, "Hayvan türü en fazla 80 karakter olabilir", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE site_reviews
            SET message = ?, pet_type = ?, rating = ?
            WHERE id = ? AND user_id = ?
            """,
            (message, pet_type, rating, review_id, user["id"]),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM site_reviews WHERE id = ? AND user_id = ?",
            (review_id, user["id"]),
        ).fetchone()
    if cursor.rowcount < 1 or not row:
        return api_response(False, "Yorum bulunamadı veya bu yorumu düzenleme yetkiniz yok", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Yorumunuz güncellendi", row_to_dict(row))


@app.route("/api/notifications", methods=["GET"])
def api_member_notifications():
    """Giriş yapan üyeye ait son bildirimleri üst menü için döndürür."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Bildirimler için üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        rows = db.execute(
            """
            SELECT id, kind, title, message, reference_type, reference_id, is_read, created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 30
            """,
            (user["id"],),
        ).fetchall()
        unread_count = first_column(db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],),
        ).fetchone())
    return api_response(
        True,
        "Bildirimler listelendi",
        {"items": [row_to_dict(row) for row in rows], "unread_count": unread_count},
    )


@app.route("/api/notifications/read", methods=["PATCH", "POST"])
def api_member_notifications_read():
    """Üst panel açıldığında üyenin okunmamış bildirimlerini okundu olarak işaretler."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Bildirimler için üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
        db.commit()
    return api_response(True, "Bildirimler okundu", {})


@app.route("/api/profile", methods=["PATCH", "PUT"])
def api_profile_update():
    """Üyenin temel profil bilgilerini güvenli şekilde günceller."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    profile_picture = (data.get("profile_picture") or "").strip()
    try:
        phone = validate_phone(data.get("phone", ""))
    except ValueError as exc:
        return api_response(False, str(exc), None, HTTPStatus.BAD_REQUEST)
    if len(full_name) < 3:
        return api_response(False, "Ad soyad en az 3 karakter olmalı", None, HTTPStatus.BAD_REQUEST)
    if profile_picture and not re.fullmatch(r"https?://[^\s]{1,500}", profile_picture):
        return api_response(False, "Profil fotoğrafı için geçerli bir URL girin", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        existing_phone = db.execute(
            "SELECT id FROM users WHERE phone = ? AND id <> ?",
            (phone, user["id"]),
        ).fetchone()
        if existing_phone:
            return api_response(False, "Bu telefon numarası başka bir üyede kayıtlı", None, HTTPStatus.CONFLICT)
        db.execute(
            "UPDATE users SET full_name = ?, name = ?, phone = ?, profile_picture = ? WHERE id = ?",
            (full_name, full_name, phone, profile_picture, user["id"]),
        )
        db.commit()
        updated = db.execute(
            """
            SELECT id, google_id, full_name, name, email, phone, profile_picture, role, created_at, is_banned
            FROM users WHERE id = ?
            """,
            (user["id"],),
        ).fetchone()
    return api_response(True, "Profil bilgileriniz güncellendi", row_to_dict(updated))


@app.route("/api/profile/pets/<int:pet_id>", methods=["PATCH", "PUT"])
def api_profile_pet_update(pet_id: int):
    """Üyenin yalnızca kendi hayvan kaydını düzenlemesine izin verir."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    species = (data.get("species") or "").strip()
    age = (data.get("age") or "").strip()
    notes = (data.get("notes") or "").strip()
    if not name or not species:
        return api_response(False, "Hayvan adı ve türü zorunlu", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        cursor = db.execute(
            """
            UPDATE pets SET name = ?, species = ?, age = ?, notes = ?
            WHERE id = ? AND user_id = ?
            """,
            (name, species, age, notes, pet_id, user["id"]),
        )
        db.commit()
        pet = db.execute(
            "SELECT id, name, species, age, notes, created_at FROM pets WHERE id = ? AND user_id = ?",
            (pet_id, user["id"]),
        ).fetchone()
    if cursor.rowcount < 1 or not pet:
        return api_response(False, "Hayvan kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Hayvan bilgileri güncellendi", row_to_dict(pet))


@app.route("/api/profile/pets/<int:pet_id>/health-records", methods=["POST"])
def api_profile_pet_health_add(pet_id: int):
    """Hayvanın e-nabız benzeri sağlık geçmişine yeni kayıt ekler."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    data = request.get_json(silent=True) or {}
    record_type_key = (data.get("record_type") or "note").strip().lower()
    record_type = PET_HEALTH_RECORD_TYPES.get(record_type_key)
    title = (data.get("title") or "").strip()
    details = (data.get("details") or "").strip()
    record_date = (data.get("record_date") or date.today().isoformat()).strip()
    if not record_type:
        return api_response(False, "Geçersiz sağlık kaydı türü", None, HTTPStatus.BAD_REQUEST)
    if len(title) < 2:
        return api_response(False, "Sağlık kaydı başlığı zorunlu", None, HTTPStatus.BAD_REQUEST)
    try:
        datetime.strptime(record_date, "%Y-%m-%d")
    except ValueError:
        return api_response(False, "Kayıt tarihi YYYY-MM-DD formatında olmalı", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        pet = db.execute("SELECT id FROM pets WHERE id = ? AND user_id = ?", (pet_id, user["id"])).fetchone()
        if not pet:
            return api_response(False, "Hayvan kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
        cursor = db.execute(
            """
            INSERT INTO pet_health_records
            (pet_id, user_id, record_type, title, details, record_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pet_id, user["id"], record_type, title, details, record_date, datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        record = db.execute(
            "SELECT id, record_type, title, details, record_date, created_at FROM pet_health_records WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return api_response(True, "Sağlık kaydı eklendi", row_to_dict(record), HTTPStatus.CREATED)


@app.route("/api/profile/pets/<int:pet_id>/health-records/<int:record_id>", methods=["DELETE"])
def api_profile_pet_health_delete(pet_id: int, record_id: int):
    """Üyenin kendi hayvanına ait sağlık kaydını siler."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        cursor = db.execute(
            "DELETE FROM pet_health_records WHERE id = ? AND pet_id = ? AND user_id = ?",
            (record_id, pet_id, user["id"]),
        )
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Sağlık kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Sağlık kaydı silindi", {})


@app.route("/api/profile/appointments/<int:appointment_id>", methods=["DELETE"])
def api_profile_appointment_delete(appointment_id: int):
    """Üyenin geçmiş, tamamlanmış veya iptal edilmiş kendi randevusunu siler."""
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        appointment = db.execute(
            """
            SELECT id, appt_date, appt_time, status
            FROM appointments
            WHERE id = ? AND user_id = ?
            """,
            (appointment_id, user["id"]),
        ).fetchone()
        if not appointment:
            return api_response(False, "Randevu bulunamadı", None, HTTPStatus.NOT_FOUND)
        try:
            appointment_at = datetime.strptime(
                f"{appointment['appt_date']} {appointment['appt_time']}",
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            return api_response(False, "Randevu tarihi geçersiz", None, HTTPStatus.BAD_REQUEST)
        if appointment_at >= datetime.now() and appointment["status"] not in {"cancelled", "completed"}:
            return api_response(
                False,
                "Yalnızca geçmiş, tamamlanmış veya iptal edilmiş randevular silinebilir",
                None,
                HTTPStatus.FORBIDDEN,
            )
        db.execute("DELETE FROM appointment_reminders WHERE appointment_id = ?", (appointment_id,))
        db.execute("DELETE FROM appointments WHERE id = ? AND user_id = ?", (appointment_id, user["id"]))
        db.commit()
    return api_response(True, "Randevu geçmişinizden silindi", {})


@app.route("/api/profile/purchased-products", methods=["GET"])
def api_profile_purchased_products():
    user = get_request_session_user()
    if not user or user["is_banned"]:
        return api_response(False, "Üye girişi gerekli", None, HTTPStatus.UNAUTHORIZED)
    with connect() as db:
        rows = db.execute(
            """
            SELECT DISTINCT products.id, products.name
            FROM orders
            JOIN order_items ON order_items.order_id = orders.id
            JOIN products ON products.id = order_items.product_id
            WHERE orders.user_id = ?
            ORDER BY products.name
            """,
            (user["id"],),
        ).fetchall()
    return api_response(True, "Satın alınan ürünler listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/site-texts", methods=["GET"])
@require_admin_api
def api_admin_site_texts():
    with connect() as db:
        rows = db.execute("SELECT text_key, label, value, updated_at FROM site_texts ORDER BY text_key").fetchall()
    return api_response(True, "Site yazıları listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/site-texts/update/<text_key>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_site_texts_update(text_key: str):
    data = request.get_json(silent=True) or {}
    value = (data.get("value") or "").strip()
    if not value:
        return api_response(False, "Metin boş olamaz", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        db.execute(
            "UPDATE site_texts SET value = ?, updated_at = ? WHERE text_key = ?",
            (value, datetime.now().isoformat(timespec="seconds"), text_key),
        )
        db.commit()
        row = db.execute("SELECT text_key, label, value, updated_at FROM site_texts WHERE text_key = ?", (text_key,)).fetchone()
    if not row:
        return api_response(False, "Site yazısı bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Site yazısı güncellendi", row_to_dict(row))


@app.route("/api/admin/reviews", methods=["GET"])
@require_admin_api
def api_admin_reviews():
    with connect() as db:
        rows = db.execute("SELECT * FROM site_reviews ORDER BY id DESC").fetchall()
    return api_response(True, "Yorumlar listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/reviews/update/<int:review_id>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_reviews_update(review_id: int):
    data = request.get_json(silent=True) or {}
    allowed = {"author", "pet_type", "rating", "message", "reply", "active"}
    updates = []
    params = []
    for field in allowed:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        return api_response(False, "Güncellenecek alan yok", None, HTTPStatus.BAD_REQUEST)
    params.append(review_id)
    with connect() as db:
        before = db.execute("SELECT * FROM site_reviews WHERE id = ?", (review_id,)).fetchone()
        if not before:
            return api_response(False, "Yorum bulunamadı", None, HTTPStatus.NOT_FOUND)
        db.execute(f"UPDATE site_reviews SET {', '.join(updates)} WHERE id = ?", params)
        if (
            "reply" in data
            and (data.get("reply") or "").strip()
            and (before["reply"] or "") != (data.get("reply") or "")
        ):
            add_user_notification(
                db,
                before["user_id"],
                "review_reply",
                "Yorumunuza yanıt geldi",
                f"{before['product_name'] or 'Genel klinik'} yorumunuza Gümüş Veteriner yanıt verdi.",
                "review",
                review_id,
            )
        db.commit()
        row = db.execute("SELECT * FROM site_reviews WHERE id = ?", (review_id,)).fetchone()
    return api_response(True, "Yorum güncellendi", row_to_dict(row))


@app.route("/api/admin/reviews/delete/<int:review_id>", methods=["DELETE"])
@require_admin_api
def api_admin_reviews_delete(review_id: int):
    """Admin uygulamasından seçilen yorumu kalıcı olarak siler."""
    with connect() as db:
        cursor = db.execute("DELETE FROM site_reviews WHERE id = ?", (review_id,))
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Yorum bulunamadı", None, HTTPStatus.NOT_FOUND)
    log_admin_action("review_delete", "review", review_id)
    return api_response(True, "Yorum silindi", {})


@app.route("/api/admin/appointment-slots", methods=["GET"])
@require_admin_api
def api_admin_appointment_slots():
    appt_date = (request.args.get("date") or date.today().isoformat()).strip()
    try:
        datetime.strptime(appt_date, "%Y-%m-%d")
    except ValueError:
        return api_response(False, "Tarih YYYY-MM-DD formatında olmalı", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        rows = appointment_slot_summary(db, appt_date)
    return api_response(True, "Randevu saatleri listelendi", rows)


@app.route("/api/admin/appointment-slots", methods=["POST", "PATCH"])
@require_admin_api
def api_admin_appointment_slots_update():
    data = request.get_json(silent=True) or {}
    appt_date = (data.get("date") or data.get("appt_date") or "").strip()
    appt_time = (data.get("time") or data.get("appt_time") or "").strip()
    try:
        datetime.strptime(appt_date, "%Y-%m-%d")
    except ValueError:
        return api_response(False, "Tarih YYYY-MM-DD formatında olmalı", None, HTTPStatus.BAD_REQUEST)
    if not re.fullmatch(r"\d{2}:\d{2}", appt_time):
        return api_response(False, "Saat HH:MM formatında olmalı", None, HTTPStatus.BAD_REQUEST)
    is_available = 1 if data.get("is_available", True) else 0
    note = (data.get("note") or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        db.execute(
            """
            INSERT INTO appointment_slots (appt_date, appt_time, is_available, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(appt_date, appt_time)
            DO UPDATE SET is_available = excluded.is_available, note = excluded.note
            """,
            (appt_date, appt_time, is_available, note, now),
        )
        db.commit()
        rows = appointment_slot_summary(db, appt_date)
    return api_response(True, "Randevu saati güncellendi", rows)


@app.route("/api/admin/users", methods=["GET"])
@require_admin_api
def api_admin_users():
    with connect() as db:
        user_rows = db.execute(
            """
            SELECT id, full_name, email, phone, role, is_banned, created_at
            FROM users
            ORDER BY created_at DESC
            """
        ).fetchall()
        users = []
        for row in user_rows:
            user = row_to_dict(row)
            user["addresses"] = [
                row_to_dict(address)
                for address in db.execute(
                    "SELECT id, title, address, city, district, created_at FROM user_addresses WHERE user_id = ? ORDER BY id DESC",
                    (row["id"],),
                ).fetchall()
            ]
            user["pets"] = [
                row_to_dict(pet)
                for pet in db.execute(
                    "SELECT id, name, species, age, notes, created_at FROM pets WHERE user_id = ? ORDER BY id DESC",
                    (row["id"],),
                ).fetchall()
            ]
            users.append(user)
    return api_response(True, "Üyeler listelendi", users)


@app.route("/api/admin/pets", methods=["GET"])
@require_admin_api
def api_admin_pets():
    """Profil kayıtlarını ve randevudan gelen yeni petleri admin uygulamasına taşır."""
    with connect() as db:
        profile_pets = db.execute(
            """
            SELECT
                'profile-' || CAST(pets.id AS TEXT) AS record_key,
                pets.id,
                pets.user_id,
                NULL AS appointment_id,
                pets.name,
                pets.species,
                '' AS breed,
                COALESCE(pets.age, '') AS age,
                COALESCE(pets.notes, '') AS notes,
                COALESCE(users.full_name, '') AS owner,
                COALESCE(users.phone, '') AS phone,
                'profile' AS source,
                pets.created_at
            FROM pets
            LEFT JOIN users ON users.id = pets.user_id
            WHERE COALESCE(pets.admin_hidden, 0) = 0
            ORDER BY pets.id DESC
            """
        ).fetchall()
        clinic_pets = db.execute(
            """
            SELECT
                'clinic-' || CAST(clinic_pets.id AS TEXT) AS record_key,
                clinic_pets.id,
                clinic_pets.user_id,
                clinic_pets.appointment_id,
                clinic_pets.name,
                clinic_pets.species,
                COALESCE(clinic_pets.breed, '') AS breed,
                COALESCE(clinic_pets.age, '') AS age,
                COALESCE(clinic_pets.notes, '') AS notes,
                COALESCE(clinic_pets.owner_name, users.full_name, '') AS owner,
                COALESCE(clinic_pets.phone, users.phone, '') AS phone,
                'clinic' AS source,
                clinic_pets.created_at
            FROM clinic_pets
            LEFT JOIN users ON users.id = clinic_pets.user_id
            WHERE COALESCE(clinic_pets.admin_hidden, 0) = 0
            ORDER BY clinic_pets.id DESC
            """
        ).fetchall()
        appointment_pets = db.execute(
            """
            SELECT
                'appointment-' || CAST(MAX(appointments.id) AS TEXT) AS record_key,
                MAX(appointments.id) AS id,
                MAX(appointments.user_id) AS user_id,
                MAX(appointments.id) AS appointment_id,
                appointments.pet_name AS name,
                appointments.pet_type AS species,
                '' AS breed,
                '' AS age,
                'Randevu ekranından eklendi' AS notes,
                TRIM(appointments.first_name || ' ' || appointments.last_name) AS owner,
                appointments.phone,
                'appointment' AS source,
                MAX(appointments.created_at) AS created_at
            FROM appointments
            WHERE appointments.pet_id IS NULL
              AND COALESCE(appointments.admin_pet_hidden, 0) = 0
              AND COALESCE(TRIM(appointments.pet_name), '') <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM clinic_pets
                  WHERE clinic_pets.appointment_id = appointments.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM pets
                  LEFT JOIN users ON users.id = pets.user_id
                  WHERE LOWER(pets.name) = LOWER(appointments.pet_name)
                    AND (
                        pets.user_id = appointments.user_id
                        OR COALESCE(users.phone, '') = COALESCE(appointments.phone, '')
                    )
              )
            GROUP BY
                appointments.pet_name,
                appointments.pet_type,
                appointments.first_name,
                appointments.last_name,
                appointments.phone
            ORDER BY MAX(appointments.id) DESC
            """
        ).fetchall()
    rows = [row_to_dict(row) for row in profile_pets]
    rows.extend(row_to_dict(row) for row in clinic_pets)
    rows.extend(row_to_dict(row) for row in appointment_pets)
    return api_response(True, "Petler listelendi", rows)


@app.route("/api/admin/pets/add", methods=["POST"])
@require_admin_api
def api_admin_pets_add():
    """Admin uygulamasından eklenen peti kalıcı klinik kaydına dönüştürür."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    species = (data.get("species") or "").strip()
    if not name or not species:
        return api_response(False, "Pet adı ve türü zorunludur", None, HTTPStatus.BAD_REQUEST)
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        cursor = db.execute(
            """
            INSERT INTO clinic_pets
            (name, species, breed, age, owner_name, phone, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                species,
                (data.get("breed") or "").strip(),
                (data.get("age") or "").strip(),
                (data.get("owner_name") or "").strip(),
                (data.get("phone") or "").strip(),
                (data.get("notes") or "").strip(),
                now,
            ),
        )
        pet = db.execute("SELECT * FROM clinic_pets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        db.commit()
    return api_response(True, "Pet kaydedildi", row_to_dict(pet), HTTPStatus.CREATED)


@app.route("/api/admin/pets/delete/<string:source>/<int:pet_id>", methods=["DELETE"])
@require_admin_api
def api_admin_pets_delete(source: str, pet_id: int):
    """Peti kullanıcı profilinden silmeden yalnızca admin listesinden gizler."""
    table_column = {
        "profile": ("pets", "admin_hidden"),
        "clinic": ("clinic_pets", "admin_hidden"),
        "appointment": ("appointments", "admin_pet_hidden"),
    }.get(source)
    if not table_column:
        return api_response(False, "Geçersiz pet kaynağı", None, HTTPStatus.BAD_REQUEST)
    table, column = table_column
    with connect() as db:
        cursor = db.execute(f"UPDATE {table} SET {column} = 1 WHERE id = ?", (pet_id,))
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Pet bulunamadı", None, HTTPStatus.NOT_FOUND)
    log_admin_action("pet_hide", "pet", pet_id, f"source={source}")
    return api_response(True, "Pet admin listesinden kaldırıldı", {})


def register_appointment_pet(db, appointment_id: int) -> dict:
    """Randevudaki peti üye profiline veya klinik pet listesine kaydeder."""
    appointment = db.execute(
        "SELECT * FROM appointments WHERE id = ?",
        (appointment_id,),
    ).fetchone()
    if not appointment:
        raise ValueError("Randevu bulunamadı")
    if not (appointment["pet_name"] or "").strip():
        raise ValueError("Randevuda pet adı bulunmuyor")
    if appointment["pet_id"]:
        pet = db.execute("SELECT * FROM pets WHERE id = ?", (appointment["pet_id"],)).fetchone()
        return {"source": "profile", **row_to_dict(pet)}
    if "clinic_pet_id" in appointment.keys() and appointment["clinic_pet_id"]:
        pet = db.execute(
            "SELECT * FROM clinic_pets WHERE id = ?",
            (appointment["clinic_pet_id"],),
        ).fetchone()
        return {"source": "clinic", **row_to_dict(pet)}

    now = datetime.now().isoformat(timespec="seconds")
    if appointment["user_id"]:
        existing = db.execute(
            """
            SELECT * FROM pets
            WHERE user_id = ? AND LOWER(name) = LOWER(?) AND LOWER(species) = LOWER(?)
            """,
            (appointment["user_id"], appointment["pet_name"], appointment["pet_type"]),
        ).fetchone()
        if existing:
            pet_id = existing["id"]
            pet = existing
        else:
            pet_id = db.execute(
                """
                INSERT INTO pets (user_id, name, species, age, notes, created_at)
                VALUES (?, ?, ?, '', 'Randevu kaydından admin tarafından eklendi', ?)
                """,
                (
                    appointment["user_id"],
                    appointment["pet_name"].strip(),
                    appointment["pet_type"].strip(),
                    now,
                ),
            ).lastrowid
            pet = db.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
        db.execute(
            "UPDATE appointments SET pet_id = ?, clinic_pet_id = NULL WHERE id = ?",
            (pet_id, appointment_id),
        )
        return {"source": "profile", **row_to_dict(pet)}

    clinic_pet_id = db.execute(
        """
        INSERT INTO clinic_pets
        (appointment_id, name, species, breed, age, owner_name, phone, notes, created_at)
        VALUES (?, ?, ?, '', '', ?, ?, 'Randevu kaydından admin tarafından eklendi', ?)
        """,
        (
            appointment_id,
            appointment["pet_name"].strip(),
            appointment["pet_type"].strip(),
            f"{appointment['first_name']} {appointment['last_name']}".strip(),
            appointment["phone"],
            now,
        ),
    ).lastrowid
    db.execute(
        "UPDATE appointments SET clinic_pet_id = ? WHERE id = ?",
        (clinic_pet_id, appointment_id),
    )
    pet = db.execute("SELECT * FROM clinic_pets WHERE id = ?", (clinic_pet_id,)).fetchone()
    return {"source": "clinic", **row_to_dict(pet)}


@app.route("/api/admin/appointments/<int:appointment_id>/add-pet", methods=["POST"])
@require_admin_api
def api_admin_appointment_add_pet(appointment_id: int):
    try:
        with connect() as db:
            pet = register_appointment_pet(db, appointment_id)
            db.commit()
    except ValueError as exc:
        return api_response(False, str(exc), None, HTTPStatus.BAD_REQUEST)
    log_admin_action("appointment_pet_add", "appointment", appointment_id)
    return api_response(True, "Pet, pet listesine eklendi", pet, HTTPStatus.CREATED)


def hospitalization_payload(db, row) -> dict:
    item = row_to_dict(row)
    previous = db.execute(
        """
        SELECT diagnosis, admitted_at, discharged_at
        FROM hospitalizations
        WHERE id <> ?
          AND status = 'discharged'
          AND (
                (pet_id IS NOT NULL AND pet_id = ?)
             OR (clinic_pet_id IS NOT NULL AND clinic_pet_id = ?)
             OR (
                  pet_id IS NULL
                  AND clinic_pet_id IS NULL
                  AND LOWER(pet_name) = LOWER(?)
                  AND COALESCE(phone, '') = COALESCE(?, '')
                )
          )
        ORDER BY admitted_at DESC
        """,
        (
            row["id"],
            row["pet_id"],
            row["clinic_pet_id"],
            row["pet_name"],
            row["phone"],
        ),
    ).fetchall()
    item["previous_stays"] = [row_to_dict(history) for history in previous]
    return item


@app.route("/api/admin/hospitalizations", methods=["GET", "POST"])
@require_admin_api
def api_admin_hospitalizations():
    if request.method == "GET":
        with connect() as db:
            rows = db.execute(
                "SELECT * FROM hospitalizations ORDER BY status = 'active' DESC, admitted_at DESC"
            ).fetchall()
            data = [hospitalization_payload(db, row) for row in rows]
        return api_response(True, "Yatan hastalar listelendi", data)

    data = request.get_json(silent=True) or {}
    record_key = (data.get("pet_record_key") or "").strip()
    pet_name = (data.get("pet_name") or "").strip()
    species = (data.get("species") or "Belirtilmedi").strip()
    owner_name = (data.get("owner_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    diagnosis = (data.get("diagnosis") or "").strip()
    treatment = (data.get("treatment") or "").strip()
    room = (data.get("room") or "Oda belirtilmedi").strip()
    notes = (data.get("notes") or "").strip()
    if (not pet_name and not record_key) or not diagnosis or not treatment:
        return api_response(
            False,
            "Pet adı, tanı/yatış nedeni ve tedavi zorunlu",
            None,
            HTTPStatus.BAD_REQUEST,
        )

    pet_id = clinic_pet_id = appointment_id = user_id = None
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        if record_key.startswith("profile-"):
            pet_id = int(record_key.removeprefix("profile-"))
            pet = db.execute(
                """
                SELECT pets.*, users.full_name AS owner_name, users.phone
                FROM pets JOIN users ON users.id = pets.user_id
                WHERE pets.id = ?
                """,
                (pet_id,),
            ).fetchone()
            if not pet:
                return api_response(False, "Kayıtlı pet bulunamadı", None, HTTPStatus.NOT_FOUND)
            user_id = pet["user_id"]
            pet_name, species = pet["name"], pet["species"]
            owner_name, phone = pet["owner_name"], pet["phone"]
        elif record_key.startswith("clinic-"):
            clinic_pet_id = int(record_key.removeprefix("clinic-"))
            pet = db.execute("SELECT * FROM clinic_pets WHERE id = ?", (clinic_pet_id,)).fetchone()
            if not pet:
                return api_response(False, "Klinik pet kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
            user_id = pet["user_id"]
            appointment_id = pet["appointment_id"]
            pet_name, species = pet["name"], pet["species"]
            owner_name, phone = pet["owner_name"], pet["phone"]
        elif record_key.startswith("appointment-"):
            appointment_id = int(record_key.removeprefix("appointment-"))
            pet = register_appointment_pet(db, appointment_id)
            if pet["source"] == "profile":
                pet_id, user_id = pet["id"], pet["user_id"]
            else:
                clinic_pet_id, user_id = pet["id"], pet.get("user_id")
            pet_name, species = pet["name"], pet["species"]
            owner_name = pet.get("owner_name") or owner_name
            phone = pet.get("phone") or phone
        elif data.get("add_to_pets", True):
            clinic_pet_id = db.execute(
                """
                INSERT INTO clinic_pets
                (name, species, breed, age, owner_name, phone, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pet_name,
                    species,
                    (data.get("breed") or "").strip(),
                    (data.get("age") or "").strip(),
                    owner_name,
                    phone,
                    "Hasta yatışı sırasında eklendi",
                    now,
                ),
            ).lastrowid

        hospitalization_id = db.execute(
            """
            INSERT INTO hospitalizations
            (pet_id, clinic_pet_id, appointment_id, user_id, pet_name, species,
             owner_name, phone, room, diagnosis, treatment, notes, status,
             admitted_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                pet_id,
                clinic_pet_id,
                appointment_id,
                user_id,
                pet_name,
                species,
                owner_name,
                phone,
                room,
                diagnosis,
                treatment,
                notes,
                data.get("admitted_at") or now,
                now,
            ),
        ).lastrowid
        db.commit()
        row = db.execute("SELECT * FROM hospitalizations WHERE id = ?", (hospitalization_id,)).fetchone()
        payload = hospitalization_payload(db, row)
    log_admin_action("hospitalization_add", "hospitalization", hospitalization_id, pet_name)
    return api_response(True, "Hasta yatışı kaydedildi", payload, HTTPStatus.CREATED)


@app.route("/api/admin/hospitalizations/<int:hospitalization_id>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_hospitalization_update(hospitalization_id: int):
    data = request.get_json(silent=True) or {}
    allowed = {"room", "diagnosis", "treatment", "notes", "owner_name", "phone"}
    updates, params = [], []
    for field in allowed:
        if field in data:
            updates.append(f"{field} = ?")
            params.append((data.get(field) or "").strip())
    if not updates:
        return api_response(False, "Güncellenecek yatış bilgisi yok", None, HTTPStatus.BAD_REQUEST)
    params.append(hospitalization_id)
    with connect() as db:
        db.execute(f"UPDATE hospitalizations SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        row = db.execute("SELECT * FROM hospitalizations WHERE id = ?", (hospitalization_id,)).fetchone()
        if not row:
            return api_response(False, "Yatış kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
        payload = hospitalization_payload(db, row)
    log_admin_action("hospitalization_update", "hospitalization", hospitalization_id)
    return api_response(True, "Yatış bilgileri güncellendi", payload)


@app.route("/api/admin/hospitalizations/<int:hospitalization_id>/discharge", methods=["POST"])
@require_admin_api
def api_admin_hospitalization_discharge(hospitalization_id: int):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        row = db.execute("SELECT * FROM hospitalizations WHERE id = ?", (hospitalization_id,)).fetchone()
        if not row:
            return api_response(False, "Yatış kaydı bulunamadı", None, HTTPStatus.NOT_FOUND)
        if row["status"] != "discharged":
            db.execute(
                "UPDATE hospitalizations SET status = 'discharged', discharged_at = ? WHERE id = ?",
                (now, hospitalization_id),
            )
            if row["pet_id"] and row["user_id"]:
                db.execute(
                    """
                    INSERT INTO pet_health_records
                    (pet_id, user_id, record_type, title, details, record_date, created_at)
                    VALUES (?, ?, 'Yatış', ?, ?, ?, ?)
                    """,
                    (
                        row["pet_id"],
                        row["user_id"],
                        row["diagnosis"],
                        f"Yatış tedavisi: {row['treatment']}\n{row['notes'] or ''}".strip(),
                        date.today().isoformat(),
                        now,
                    ),
                )
        db.commit()
        updated = db.execute("SELECT * FROM hospitalizations WHERE id = ?", (hospitalization_id,)).fetchone()
        payload = hospitalization_payload(db, updated)
    log_admin_action("hospitalization_discharge", "hospitalization", hospitalization_id)
    return api_response(True, "Hasta taburcu edildi", payload)


@app.route("/api/admin/dashboard", methods=["GET"])
@require_admin_api
def api_admin_dashboard():
    now = datetime.now()
    month_keys = []
    cursor = date(now.year, now.month, 1)
    for _ in range(6):
        month_keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=1) - timedelta(days=1)).replace(day=1)
    month_keys.reverse()
    with connect() as db:
        orders = db.execute(
            "SELECT id, total, status, created_at FROM orders ORDER BY id DESC"
        ).fetchall()
        monthly = {key: 0.0 for key in month_keys}
        for order in orders:
            key = str(order["created_at"])[:7]
            if key in monthly and order["status"] != "cancelled":
                monthly[key] += float(order["total"] or 0)
        best = db.execute(
            """
            SELECT products.id, products.name, SUM(order_items.quantity) AS quantity
            FROM order_items
            JOIN products ON products.id = order_items.product_id
            JOIN orders ON orders.id = order_items.order_id
            WHERE orders.status <> 'cancelled'
            GROUP BY products.id, products.name
            ORDER BY quantity DESC
            LIMIT 1
            """
        ).fetchone()
        low_stock = db.execute(
            "SELECT id, name, stock FROM products WHERE active = 1 AND stock <= 5 ORDER BY stock, name"
        ).fetchall()
        pending_orders = db.execute(
            "SELECT id, first_name, last_name, total, created_at FROM orders WHERE status = 'pending' ORDER BY id DESC LIMIT 5"
        ).fetchall()
        pending_appointments = db.execute(
            """
            SELECT id, first_name, last_name, pet_name, appt_date, appt_time
            FROM appointments WHERE status = 'pending'
            ORDER BY appt_date, appt_time LIMIT 5
            """
        ).fetchall()
        unanswered = first_column(db.execute(
            "SELECT COUNT(*) FROM contacts WHERE COALESCE(reply, '') = ''"
        ).fetchone())
        # Pet Listesi ekranı profil petlerini, klinik petlerini ve henüz kalıcı
        # kayda çevrilmemiş randevu petlerini birlikte gösterir. Dashboard da
        # aynı kaynağı saymalı; aksi halde iki ekrandaki toplamlar farklı olur.
        unregistered_appointment_pets = first_column(
            db.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT
                        LOWER(appointments.pet_name),
                        LOWER(appointments.pet_type),
                        appointments.phone
                    FROM appointments
                    WHERE appointments.pet_id IS NULL
                      AND appointments.clinic_pet_id IS NULL
                      AND COALESCE(TRIM(appointments.pet_name), '') <> ''
                      AND NOT EXISTS (
                          SELECT 1
                          FROM pets
                          JOIN users ON users.id = pets.user_id
                          WHERE LOWER(pets.name) = LOWER(appointments.pet_name)
                            AND LOWER(pets.species) = LOWER(appointments.pet_type)
                            AND users.phone = appointments.phone
                      )
                    GROUP BY
                        LOWER(appointments.pet_name),
                        LOWER(appointments.pet_type),
                        appointments.phone
                ) AS unregistered_pets
                """
            ).fetchone()
        )
        total_pets = (
            first_column(db.execute("SELECT COUNT(*) FROM pets").fetchone())
            + first_column(db.execute("SELECT COUNT(*) FROM clinic_pets").fetchone())
            + unregistered_appointment_pets
        )
        active_hospitalizations = first_column(db.execute(
            "SELECT COUNT(*) FROM hospitalizations WHERE status = 'active'"
        ).fetchone())

    current_total = monthly.get(now.strftime("%Y-%m"), 0.0)
    previous_key = (date(now.year, now.month, 1) - timedelta(days=1)).strftime("%Y-%m")
    previous_total = monthly.get(previous_key, 0.0)
    sales_change = (
        round(((current_total - previous_total) / previous_total) * 100, 1)
        if previous_total > 0
        else (100.0 if current_total > 0 else 0.0)
    )
    notifications = []
    notifications.extend(
        {
            "kind": "order",
            "title": f"Yeni sipariş #{row['id']}",
            "message": f"{row['first_name']} {row['last_name']} • ₺{float(row['total']):.2f}",
        }
        for row in pending_orders
    )
    notifications.extend(
        {
            "kind": "appointment",
            "title": f"Randevu #{row['id']}",
            "message": f"{row['appt_date']} {row['appt_time']} • {row['pet_name'] or row['first_name']}",
        }
        for row in pending_appointments
    )
    notifications.extend(
        {
            "kind": "stock",
            "title": "Stok uyarısı",
            "message": f"{row['name']} • kalan {row['stock']}",
        }
        for row in low_stock
    )
    if unanswered:
        notifications.append(
            {
                "kind": "contact",
                "title": "Yanıt bekleyen sorular",
                "message": f"{unanswered} müşteri mesajı yanıt bekliyor",
            }
        )
    return api_response(
        True,
        "Dashboard verileri hazır",
        {
            "total_pets": total_pets,
            "active_hospitalizations": active_hospitalizations,
            "monthly_sales": [
                {"month": key, "total": round(value, 2)}
                for key, value in monthly.items()
            ],
            "current_month_sales": round(current_total, 2),
            "sales_change_percent": sales_change,
            "best_selling_product": row_to_dict(best) if best else None,
            "low_stock": [row_to_dict(row) for row in low_stock],
            "notifications": notifications[:15],
        },
    )


@app.route("/api/admin/contacts", methods=["GET"])
@require_admin_api
def api_admin_contacts():
    with connect() as db:
        rows = db.execute("SELECT * FROM contacts ORDER BY id DESC").fetchall()
    return api_response(True, "İletişim mesajları listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/contacts/reply/<int:contact_id>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_contacts_reply(contact_id: int):
    data = request.get_json(silent=True) or {}
    reply = (data.get("reply") or "").strip()
    if len(reply) < 5:
        return api_response(False, "Yanıt en az 5 karakter olmalı", None, HTTPStatus.BAD_REQUEST)
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        contact = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not contact:
            return api_response(False, "Mesaj bulunamadı", None, HTTPStatus.NOT_FOUND)
        db.execute("UPDATE contacts SET reply = ?, replied_at = ? WHERE id = ?", (reply, now, contact_id))
        db.commit()
        updated = row_to_dict(db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())
    subject = f"Gümüş Veteriner yanıtı: {updated.get('subject') or 'İletişim mesajınız'}"
    body = (
        f"Merhaba {updated.get('full_name', '')},\n\n"
        f"Mesajınız:\n{updated.get('message', '')}\n\n"
        f"Yanıtımız:\n{reply}\n\n"
        "Gümüş Veteriner Muayenehanesi\n0546 136 14 33"
    )
    mail_result = send_email(updated.get("email", ""), subject, body)
    updated["mail"] = {"success": mail_result.success, "message": mail_result.message}
    return api_response(True, "Yanıt kaydedildi ve mail gönderimi denendi", updated)


@app.route("/api/admin/users/update/<int:user_id>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_users_update(user_id: int):
    data = request.get_json(silent=True) or {}
    updates = []
    params = []
    if "role" in data:
        if data["role"] not in {"member", "admin"}:
            return api_response(False, "Geçersiz rol", None, HTTPStatus.BAD_REQUEST)
        updates.append("role = ?")
        params.append(data["role"])
    if "is_banned" in data:
        updates.append("is_banned = ?")
        params.append(1 if data["is_banned"] else 0)
    if not updates:
        return api_response(False, "Güncellenecek alan yok", None, HTTPStatus.BAD_REQUEST)
    params.append(user_id)
    with connect() as db:
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        if data.get("is_banned"):
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        db.commit()
        row = db.execute("SELECT id, full_name, email, phone, role, is_banned, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return api_response(False, "Üye bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Üye güncellendi", row_to_dict(row))


@app.route("/api/admin/users/delete/<int:user_id>", methods=["DELETE"])
@require_admin_api
def api_admin_users_delete(user_id: int):
    with connect() as db:
        row = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return api_response(False, "Üye bulunamadı", None, HTTPStatus.NOT_FOUND)
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM user_addresses WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        db.execute("UPDATE site_reviews SET user_id = NULL WHERE user_id = ?", (user_id,))
        db.execute("UPDATE orders SET user_id = NULL WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    return api_response(True, "Üye silindi", {})


@app.route("/api/admin/orders", methods=["GET"])
@require_admin_api
def api_admin_orders():
    with connect() as db:
        rows = db.execute(
            "SELECT id FROM orders WHERE COALESCE(admin_hidden, 0) = 0 ORDER BY created_at DESC"
        ).fetchall()
        orders = [order_with_items(db, row["id"]) for row in rows]
    return api_response(True, "Siparişler listelendi", [order for order in orders if order])


@app.route("/api/admin/orders/update/<int:order_id>", methods=["PATCH", "PUT"])
@require_admin_api
def api_admin_orders_update(order_id: int):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    allowed = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
    if status not in allowed:
        return api_response(False, "Geçersiz sipariş durumu", None, HTTPStatus.BAD_REQUEST)
    mail_result = None
    with connect() as db:
        before = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not before:
            return api_response(False, "Sipariş bulunamadı", None, HTTPStatus.NOT_FOUND)
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        if before["status"] != status:
            order_message = {
                "confirmed": "Siparişiniz onaylandı ve hazırlanıyor.",
                "shipped": "Siparişiniz kargoya verildi.",
                "delivered": "Siparişiniz teslim edildi.",
                "cancelled": "Siparişiniz iptal edildi.",
            }.get(status)
            if order_message:
                add_user_notification(
                    db,
                    order_with_items(db, order_id).get("user_id"),
                    "order_status",
                    "Sipariş durumunuz güncellendi",
                    order_message,
                    "order",
                    order_id,
                )
        db.commit()
        order = order_with_items(db, order_id)
    if order and before["status"] != status:
        mail_result = send_order_status_email(order, status)
        if mail_result and not mail_result.success:
            security_logger.error(
                "order_status_mail_failed order_id=%s email=%s status=%s detail=%s",
                order_id,
                order.get("notification_email") or order.get("email", ""),
                status,
                mail_result.detail or mail_result.message,
            )
    elif order:
        mail_result = EmailResult(
            False,
            "E-posta gönderilmedi",
            "Sipariş durumu değişmediği için yeni bildirim oluşturulmadı",
        )
    data_payload = order or {}
    if mail_result:
        data_payload["mail"] = {
            "success": mail_result.success,
            "message": mail_result.message,
            "detail": mail_result.detail,
            "recipient": (
                order.get("notification_email") or order.get("email", "")
                if order
                else ""
            ),
        }
    return api_response(True, "Sipariş durumu güncellendi", data_payload)


@app.route("/api/admin/orders/delete/<int:order_id>", methods=["DELETE"])
@require_admin_api
def api_admin_orders_delete(order_id: int):
    """Sipariş geçmişini kullanıcıdan silmeden admin görünümünden kaldırır."""
    with connect() as db:
        cursor = db.execute("UPDATE orders SET admin_hidden = 1 WHERE id = ?", (order_id,))
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Sipariş bulunamadı", None, HTTPStatus.NOT_FOUND)
    log_admin_action("order_hide", "order", order_id)
    return api_response(True, "Sipariş admin listesinden kaldırıldı", {})


@app.route("/api/admin/send-sms", methods=["POST"])
@require_admin_api
@limiter.limit("30 per hour")
def api_admin_send_sms():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    message = data.get("message") or ""
    try:
        normalize_tr_phone(phone)
        validate_sms_message(message)
    except ValueError as exc:
        return api_response(False, str(exc), None, HTTPStatus.BAD_REQUEST)

    result = send_sms(phone, message)
    if result.success:
        return api_response(True, "SMS gönderildi", {})
    return api_response(False, "SMS gönderilemedi", None, HTTPStatus.BAD_REQUEST)


@app.route("/api/admin/login", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("20 per hour")
def api_admin_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return api_response(False, "Kullanıcı adı ve şifre zorunlu", None, HTTPStatus.BAD_REQUEST)

    with connect() as db:
        admin = db.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            log_admin_login_attempt(username, True)
            token = create_admin_jwt(admin["id"], admin["username"])
            data_payload = {"token": token, "admin": {"id": admin["id"], "username": admin["username"]}}
            response, status = api_response(True, "Admin girişi başarılı", data_payload)
            response["token"] = token
            response["user"] = {"id": admin["id"], "full_name": admin["username"], "email": admin["username"], "role": "admin"}
            return response, status

        legacy = db.execute("SELECT * FROM users WHERE email = ?", (username.lower(),)).fetchone()
        if legacy and legacy["role"] == "admin" and not legacy["is_banned"] and verify_password(password, legacy["password_hash"], legacy["password_salt"]):
            log_admin_login_attempt(username, True)
            token = create_admin_jwt(legacy["id"], legacy["email"])
            data_payload = {"token": token, "admin": {"id": legacy["id"], "username": legacy["email"]}}
            response, status = api_response(True, "Admin girişi başarılı", data_payload)
            response["token"] = token
            response["user"] = {"id": legacy["id"], "full_name": legacy["full_name"], "email": legacy["email"], "role": "admin"}
            return response, status

    log_admin_login_attempt(username, False)
    return api_response(False, "Kullanıcı adı veya şifre hatalı", None, HTTPStatus.UNAUTHORIZED)


@app.route("/api/admin/logout", methods=["POST"])
@require_admin_api
def api_admin_logout():
    return api_response(True, "Çıkış yapıldı", {})


@app.route("/api/admin/profile", methods=["GET", "PATCH", "PUT"])
@require_admin_api
def api_admin_profile():
    payload = decode_admin_jwt(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    username = (payload or {}).get("username", "")
    if request.method == "GET":
        return api_response(True, "Admin profili", {"username": username, "email": username})

    data = request.get_json(silent=True) or {}
    new_username = (data.get("username") or data.get("email") or username).strip().lower()
    new_password = (data.get("password") or "").strip()
    try:
        validate_email(new_username)
        password_hash = generate_password_hash(new_password) if new_password else None
    except ValueError as exc:
        return api_response(False, str(exc), None, HTTPStatus.BAD_REQUEST)

    with connect() as db:
        admin = db.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        if not admin:
            return api_response(False, "Admin bulunamadı", None, HTTPStatus.NOT_FOUND)
        if password_hash:
            db.execute("UPDATE admins SET username = ?, password_hash = ? WHERE id = ?", (new_username, password_hash, admin["id"]))
        else:
            db.execute("UPDATE admins SET username = ? WHERE id = ?", (new_username, admin["id"]))
        db.commit()
    token = create_admin_jwt(admin["id"], new_username)
    return api_response(True, "Admin profili güncellendi", {"token": token, "admin": {"id": admin["id"], "username": new_username}})


@app.route("/api/admin/products", methods=["GET"])
@require_admin_api
def api_admin_products():
    with connect() as db:
        rows = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return api_response(True, "Ürünler listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/products/add", methods=["POST"])
@require_admin_api
def api_admin_products_add():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "Genel").strip()
    if not name:
        return api_response(False, "Ürün adı zorunlu", None, HTTPStatus.BAD_REQUEST)
    try:
        price = float(data.get("price") or 0)
        stock = int(data.get("stock") or 0)
    except (TypeError, ValueError):
        return api_response(False, "Fiyat ve stok sayısal olmalı", None, HTTPStatus.BAD_REQUEST)
    if price < 0 or stock < 0:
        return api_response(False, "Fiyat ve stok negatif olamaz", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO products (name, category, price, stock, image_url, active) VALUES (?, ?, ?, ?, ?, ?)",
            (name, category, price, stock, (data.get("image_url") or "").strip(), 1 if data.get("active", 1) else 0),
        )
        db.commit()
        product = row_to_dict(db.execute("SELECT * FROM products WHERE id = ?", (cursor.lastrowid,)).fetchone())
    log_admin_action("product_add", "product", product["id"], product["name"])
    return api_response(True, "Ürün eklendi", product, HTTPStatus.CREATED)


@app.route("/api/admin/products/update/<int:product_id>", methods=["PUT", "PATCH"])
@require_admin_api
def api_admin_products_update(product_id: int):
    data = request.get_json(silent=True) or {}
    try:
        if "price" in data:
            data["price"] = float(data["price"])
        if "stock" in data:
            data["stock"] = int(data["stock"])
    except (TypeError, ValueError):
        return api_response(False, "Fiyat ve stok sayısal olmalı", None, HTTPStatus.BAD_REQUEST)
    if data.get("price", 0) < 0 or data.get("stock", 0) < 0:
        return api_response(False, "Fiyat ve stok negatif olamaz", None, HTTPStatus.BAD_REQUEST)
    allowed = {"name", "category", "price", "stock", "image_url", "active"}
    updates = []
    params = []
    for field in allowed:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        return api_response(False, "Güncellenecek alan yok", None, HTTPStatus.BAD_REQUEST)
    params.append(product_id)
    with connect() as db:
        db.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        return api_response(False, "Ürün bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Ürün güncellendi", row_to_dict(product))


@app.route("/api/admin/products/delete/<int:product_id>", methods=["DELETE"])
@require_admin_api
def api_admin_products_delete(product_id: int):
    with connect() as db:
        cursor = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Ürün bulunamadı", None, HTTPStatus.NOT_FOUND)
    log_admin_action("product_delete", "product", product_id)
    return api_response(True, "Ürün silindi", {})


@app.route("/api/admin/services", methods=["GET"])
@require_admin_api
def api_admin_services():
    with connect() as db:
        rows = db.execute("SELECT * FROM services ORDER BY id DESC").fetchall()
    return api_response(True, "Hizmetler listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/services/add", methods=["POST"])
@require_admin_api
def api_admin_services_add():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return api_response(False, "Hizmet adı zorunlu", None, HTTPStatus.BAD_REQUEST)
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO services (name, description, price, active, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, (data.get("description") or "").strip(), float(data.get("price") or 0), 1 if data.get("active", 1) else 0, datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        service = row_to_dict(db.execute("SELECT * FROM services WHERE id = ?", (cursor.lastrowid,)).fetchone())
    return api_response(True, "Hizmet eklendi", service, HTTPStatus.CREATED)


@app.route("/api/admin/services/update/<int:service_id>", methods=["PUT", "PATCH"])
@require_admin_api
def api_admin_services_update(service_id: int):
    data = request.get_json(silent=True) or {}
    allowed = {"name", "description", "price", "active"}
    updates = []
    params = []
    for field in allowed:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        return api_response(False, "Güncellenecek alan yok", None, HTTPStatus.BAD_REQUEST)
    params.append(service_id)
    with connect() as db:
        db.execute(f"UPDATE services SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        service = db.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not service:
        return api_response(False, "Hizmet bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Hizmet güncellendi", row_to_dict(service))


@app.route("/api/admin/services/delete/<int:service_id>", methods=["DELETE"])
@require_admin_api
def api_admin_services_delete(service_id: int):
    with connect() as db:
        cursor = db.execute("DELETE FROM services WHERE id = ?", (service_id,))
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Hizmet bulunamadı", None, HTTPStatus.NOT_FOUND)
    return api_response(True, "Hizmet silindi", {})


@app.route("/api/admin/appointments", methods=["GET"])
@require_admin_api
def api_admin_appointments():
    with connect() as db:
        rows = db.execute(
            """
            SELECT appointments.*,
                   CASE
                     WHEN appointments.pet_id IS NOT NULL
                       OR appointments.clinic_pet_id IS NOT NULL
                     THEN 1 ELSE 0
                   END AS pet_registered
            FROM appointments
            WHERE COALESCE(appointments.admin_hidden, 0) = 0
            ORDER BY appointments.created_at DESC
            """
        ).fetchall()
    return api_response(True, "Randevular listelendi", [row_to_dict(row) for row in rows])


@app.route("/api/admin/appointments/update/<int:appointment_id>", methods=["PUT", "PATCH"])
@require_admin_api
def api_admin_appointments_update(appointment_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"pending", "confirmed", "cancelled", "completed"}:
        return api_response(False, "Geçersiz randevu durumu", None, HTTPStatus.BAD_REQUEST)
    mail_result = None
    with connect() as db:
        before = db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if not before:
            return api_response(False, "Randevu bulunamadı", None, HTTPStatus.NOT_FOUND)
        db.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id))
        if before["status"] != status:
            appointment_message = {
                "pending": f"{before['appt_date']} {before['appt_time']} tarihli randevunuz onay bekliyor.",
                "confirmed": f"{before['appt_date']} {before['appt_time']} tarihli randevunuz onaylandı.",
                "cancelled": f"{before['appt_date']} {before['appt_time']} tarihli randevunuz iptal edildi.",
                "completed": f"{before['appt_date']} {before['appt_time']} tarihli randevunuz tamamlandı.",
            }.get(status)
            if appointment_message:
                add_user_notification(
                    db,
                    before["user_id"],
                    "appointment_status",
                    "Randevu durumunuz güncellendi",
                    appointment_message,
                    "appointment",
                    appointment_id,
                )
        db.commit()
        appointment_payload = appointment_with_contact(db, appointment_id)
    if before["status"] != status:
        mail_result = send_appointment_status_email(appointment_payload, status)
        if not mail_result.success:
            security_logger.error(
                "appointment_mail_failed appointment_id=%s email=%s detail=%s",
                appointment_id,
                appointment_payload.get("notification_email")
                or appointment_payload.get("email", ""),
                mail_result.detail or mail_result.message,
            )
    else:
        mail_result = EmailResult(
            False,
            "E-posta gönderilmedi",
            "Randevu durumu değişmediği için yeni bildirim oluşturulmadı",
        )
    appointment_payload["mail"] = {
        "success": mail_result.success,
        "message": mail_result.message,
        "detail": mail_result.detail,
        "recipient": (
            appointment_payload.get("notification_email")
            or appointment_payload.get("email")
            or ""
        ),
    }
    log_admin_action("appointment_update", "appointment", appointment_id, f"status={status}")
    return api_response(True, "Randevu güncellendi", appointment_payload)


@app.route("/api/admin/appointments/delete/<int:appointment_id>", methods=["DELETE"])
@require_admin_api
def api_admin_appointments_delete(appointment_id: int):
    with connect() as db:
        cursor = db.execute(
            "UPDATE appointments SET admin_hidden = 1 WHERE id = ?",
            (appointment_id,),
        )
        db.commit()
    if cursor.rowcount < 1:
        return api_response(False, "Randevu bulunamadı", None, HTTPStatus.NOT_FOUND)
    log_admin_action("appointment_delete", "appointment", appointment_id)
    return api_response(True, "Randevu admin listesinden kaldırıldı", {})


@app.route("/api/<path:_path>", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
@limiter.limit("5 per minute", exempt_when=lambda: request.path not in {"/api/login", "/api/register"})
@limiter.limit("50 per hour", exempt_when=lambda: request.path not in {"/api/login", "/api/register"})
@limiter.limit("300 per minute")
def flask_api(_path: str) -> Response:
    # /api/... istekleri eski handler'in GET/POST/PATCH/DELETE metotlarına yönlendirilir.
    if request.method == "OPTIONS":
        return Response(status=int(HTTPStatus.NO_CONTENT))
    adapter = FlaskGumusVeterinerAdapter(request.full_path.rstrip("?"))
    if request.method == "GET":
        adapter.handle_api_get(urlparse(adapter.path))
    elif request.method == "POST":
        adapter.do_POST()
    elif request.method == "PATCH":
        adapter.do_PATCH()
    elif request.method == "DELETE":
        adapter.do_DELETE()
    return adapter.flask_response()


@app.route("/<path:filename>")
def serve_project_file(filename: str) -> Response | str:
    # Kaynak kodu, .env dosyasını ve veritabanını web üzerinden yayınlama.
    # Yalnızca açıkça izin verilen statik dosyalar servis edilir.
    target = (ROOT / filename).resolve()
    allowed_file = filename == "logo.jpeg" or filename.startswith("static/")
    if allowed_file and ROOT in target.parents and target.is_file():
        return send_from_directory(ROOT, filename)
    return render_template("index.html", asset_version=DEPLOY_VERSION, csrf_token=get_csrf_token())


def main() -> None:
    ensure_database_directory()
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), GumusVeterinerHandler)
    print(f"Gümüş Veteriner çalışıyor: http://localhost:{PORT}")
    print("Durdurmak için Ctrl + C")
    server.serve_forever()


if __name__ == "__main__":
    # Local çalıştırma ve Railway için port ayarı. Canlı ortamda debug kapalı.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

