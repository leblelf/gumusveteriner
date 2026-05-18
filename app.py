from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Flask, Response, request, send_from_directory


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "gumus_veteriner.db"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5000))
app = Flask(__name__, static_folder=None)


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TEXT NOT NULL
            );

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
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
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
                created_at TEXT NOT NULL,
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
            """
        )
        seed_admin(db)
        ensure_column(db, "users", "is_banned", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "orders", "user_id", "INTEGER")
        ensure_column(db, "orders", "payment_last4", "TEXT")
        ensure_column(db, "orders", "payment_status", "TEXT")
        db.commit()


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def validate_phone(phone: str) -> str:
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
    if len(password or "") < 6:
        raise ValueError("Sifre en az 6 karakter olmali")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    candidate, _ = hash_password(password, bytes.fromhex(password_salt))
    return hmac.compare_digest(candidate, password_hash)


def seed_admin(db: sqlite3.Connection) -> None:
    email = "admin@gumusveteriner.com"
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return
    password_hash, password_salt = hash_password("admin123")
    db.execute(
        """
        INSERT INTO users (full_name, email, phone, password_hash, password_salt, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Gümüş Veteriner Admin",
            email,
            "",
            password_hash,
            password_salt,
            "admin",
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def validate_appointment(data: dict) -> dict:
    required = ["first_name", "last_name", "phone", "pet_type", "service", "appt_date", "appt_time"]
    for field in required:
        if not str(data.get(field, "")).strip():
            raise ValueError(f"{field} alani zorunlu")

    data["phone"] = validate_phone(data["phone"])
    try:
        selected = datetime.strptime(data["appt_date"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Tarih YYYY-MM-DD formatinda olmali") from exc

    if selected < date.today():
        raise ValueError("Gecmis tarih secilemez")
    if selected > date.today() + timedelta(days=60):
        raise ValueError("En fazla 60 gun ileriye randevu alinabilir")
    return data


class GumusVeterinerHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path in {"/", "/admin/login", "/admin", "/403"}:
            return str(ROOT / "templates" / "index.html")
        return str(ROOT / parsed.path.lstrip("/"))

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
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
            self.send_json({"error": "Gecersiz durum"}, HTTPStatus.BAD_REQUEST)
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
                SELECT users.id, users.full_name, users.email, users.phone, users.role, users.created_at
                , users.is_banned
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

    def require_admin(self) -> bool:
        user = self.get_session_user()
        if not user or user["role"] != "admin":
            self.send_json({"error": "Admin girisi gerekli"}, HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def require_user(self) -> sqlite3.Row | None:
        user = self.get_session_user()
        if not user:
            self.send_json({"error": "Uye girisi gerekli"}, HTTPStatus.UNAUTHORIZED)
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
                    "total_appointments": db.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
                    "pending_appointments": db.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'").fetchone()[0],
                    "total_orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                    "total_revenue": db.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()[0],
                    "total_products": db.execute("SELECT COUNT(*) FROM products WHERE active = 1").fetchone()[0],
                    "low_stock_products": db.execute("SELECT COUNT(*) FROM products WHERE stock < 10 AND active = 1").fetchone()[0],
                    "total_users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                    "active_users": db.execute("SELECT COUNT(DISTINCT user_id) FROM sessions").fetchone()[0],
                    "banned_users": db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0],
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
            self.send_json(
                {
                    "user": row_to_dict(user),
                    "addresses": [row_to_dict(row) for row in addresses],
                    "pets": [row_to_dict(row) for row in pets],
                }
            )
            return

        self.send_json({"error": "Endpoint bulunamadi"}, HTTPStatus.NOT_FOUND)

    def create_appointment(self) -> None:
        try:
            data = validate_appointment(self.read_json())
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        now = datetime.now().isoformat(timespec="seconds")
        with connect() as db:
            cursor = db.execute(
                """
                INSERT INTO appointments
                (first_name, last_name, phone, email, pet_type, pet_name, service, appt_date, appt_time, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
            appointment_id = cursor.lastrowid
            self.create_reminder_rows(db, appointment_id, data)
            db.commit()
            row = db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        self.send_json(row_to_dict(row), HTTPStatus.CREATED)

    def create_reminder_rows(self, db: sqlite3.Connection, appointment_id: int, data: dict) -> None:
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
        try:
            data = self.read_json()
            user = self.get_session_user()
            items = data.get("items") or []
            if not items:
                raise ValueError("Sepet bos")
            card_number = re.sub(r"\D+", "", data.get("card_number", ""))
            card_name = (data.get("card_name") or "").strip()
            card_expiry = (data.get("card_expiry") or "").strip()
            card_cvc = re.sub(r"\D+", "", data.get("card_cvc", ""))
            if not card_name or not re.fullmatch(r"\d{12,19}", card_number):
                raise ValueError("Gecerli kart bilgisi girin")
            if not re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*\d{2}", card_expiry):
                raise ValueError("Son kullanma tarihi AA/YY formatinda olmali")
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
                    self.send_json({"error": "Miktar en az 1 olmali"}, HTTPStatus.BAD_REQUEST)
                    return
                product = db.execute("SELECT * FROM products WHERE id = ? AND active = 1", (product_id,)).fetchone()
                if not product:
                    self.send_json({"error": f"Urun bulunamadi: {product_id}"}, HTTPStatus.NOT_FOUND)
                    return
                if product["stock"] < quantity:
                    self.send_json({"error": f"{product['name']} icin yeterli stok yok"}, HTTPStatus.BAD_REQUEST)
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
                for row in db.execute("SELECT product_id, quantity, unit_price FROM order_items WHERE order_id = ?", (order_id,))
            ]
        self.send_json(order, HTTPStatus.CREATED)

    def create_address(self) -> None:
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
                raise ValueError("Mesaj en az 10 karakter olmali")
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
                db.commit()
                user = db.execute(
                    "SELECT id, full_name, email, phone, role, created_at FROM users WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
        except sqlite3.IntegrityError:
            self.send_json({"error": "Bu email ile kayitli bir uye zaten var"}, HTTPStatus.CONFLICT)
            return

        self.send_json(row_to_dict(user), HTTPStatus.CREATED)

    def login_user(self, required_role: str) -> None:
        try:
            data = self.read_json()
            email = validate_email(data.get("email", ""))
            password = data.get("password", "")
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
                message = "Bu panel yalnizca yoneticiler icindir." if user and user["role"] != required_role and required_role == "admin" else "Email veya sifre hatali"
                if user and user["is_banned"]:
                    message = "Hesabiniz pasif hale getirildi."
                self.send_json({"error": message}, HTTPStatus.UNAUTHORIZED)
                return

            token = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sessions (token, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                (token, user["id"], user["role"], datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()

        self.send_json(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "phone": user["phone"],
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
        self.send_json({"message": "Cikis yapildi"})

    def update_admin_user(self, user_id: int) -> None:
        try:
            data = self.read_json()
        except json.JSONDecodeError:
            self.send_json({"error": "Gecersiz JSON"}, HTTPStatus.BAD_REQUEST)
            return

        updates = []
        params = []
        if "role" in data:
            if data["role"] not in {"member", "admin"}:
                self.send_json({"error": "Gecersiz rol"}, HTTPStatus.BAD_REQUEST)
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
            self.send_json({"error": "Kullanici bulunamadi"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(row_to_dict(user))

    def delete_admin_user(self, user_id: int) -> None:
        with connect() as db:
            user = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                self.send_json({"error": "Kullanici bulunamadi"}, HTTPStatus.NOT_FOUND)
                return
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM user_addresses WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
        self.send_json({"message": "Kullanici silindi"})


class FlaskGumusVeterinerAdapter(GumusVeterinerHandler):
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
def ensure_database_ready() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    init_db()


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/")
@app.route("/admin")
@app.route("/admin/login")
@app.route("/403")
def serve_app_index() -> Response:
    return send_from_directory(ROOT / "templates", "index.html")


@app.route("/api/<path:_path>", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
def flask_api(_path: str) -> Response:
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
def serve_project_file(filename: str) -> Response:
    target = ROOT / filename
    if target.is_file():
        return send_from_directory(ROOT, filename)
    return send_from_directory(ROOT / "templates", "index.html")


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), GumusVeterinerHandler)
    print(f"Gumus Veteriner calisiyor: http://localhost:{PORT}")
    print("Durdurmak icin Ctrl + C")
    server.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

