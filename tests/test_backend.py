import gc
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DB = Path(tempfile.gettempdir()) / "gumus_veteriner_backend_test.db"
os.environ.setdefault("SECRET_KEY", "backend-test-secret-key")
os.environ.setdefault("JWT_SECRET", "backend-test-jwt-secret")
os.environ["SQLITE_DB_PATH"] = str(TEST_DB)

import app as application  # noqa: E402


class BackendSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        application.ensure_database_initialized()
        cls.client = application.app.test_client()

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{TEST_DB}{suffix}")
            for attempt in range(5):
                try:
                    if path.exists():
                        path.unlink()
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    gc.collect()
                    time.sleep(0.1)

    def test_health_endpoint_reports_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["database_type"], "sqlite")
        self.assertEqual(payload["data"]["mail_provider"], "smtp")
        self.assertNotIn("SMTP_PASSWORD", payload["data"])
        self.assertIn("mail_sender", payload["data"])
        self.assertIn("mail_app_password_format_valid", payload["data"])

    def test_phone_validation_normalizes_turkish_number(self):
        self.assertEqual(
            application.validate_phone("0546 136 14 33"),
            "05461361433",
        )

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValueError):
            application.validate_email("gecersiz-adres")

    def test_admin_endpoint_requires_token(self):
        response = self.client.get("/api/admin/products")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_logo_and_seo_metadata_are_public(self):
        logo_response = self.client.get("/static/logo.jpeg")
        self.assertEqual(logo_response.status_code, 200)
        self.assertEqual(logo_response.mimetype, "image/jpeg")
        self.assertGreater(len(logo_response.data), 1000)

        home_response = self.client.get("/")
        html = home_response.get_data(as_text=True)
        self.assertIn(
            '<link rel="icon" href="/static/logo.jpeg" type="image/jpeg">',
            html,
        )
        self.assertIn('"@type": "VeterinaryCare"', html)
        self.assertIn('"@type": "WebSite"', html)
        self.assertIn(
            '<meta property="og:image" content="https://wwwgumusvet.com/static/logo.jpeg">',
            html,
        )

    def test_sitemap_and_robots_publish_logo_url(self):
        robots = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Allow: /static/logo.jpeg", robots)
        self.assertIn(
            "Sitemap: https://wwwgumusvet.com/sitemap.xml",
            robots,
        )

        sitemap_response = self.client.get("/sitemap.xml")
        sitemap = sitemap_response.get_data(as_text=True)
        self.assertEqual(sitemap_response.mimetype, "application/xml")
        self.assertIn(
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"',
            sitemap,
        )
        self.assertIn(
            "<image:loc>https://wwwgumusvet.com/static/logo.jpeg</image:loc>",
            sitemap,
        )

    def test_forgot_password_creates_hashed_single_use_token_and_sends_mail(self):
        email = "mail-test@example.com"
        password_hash, password_salt = application.hash_password("Test123*")
        with application.connect() as db:
            db.execute("DELETE FROM password_resets")
            db.execute("DELETE FROM users WHERE email = ?", (email,))
            cursor = db.execute(
                """
                INSERT INTO users
                (full_name, email, phone, password_hash, password_salt, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Mail Test",
                    email,
                    "05000000001",
                    password_hash,
                    password_salt,
                    "2026-06-14T10:00:00",
                ),
            )
            user_id = cursor.lastrowid
            db.commit()

        with patch(
            "app.send_email",
            return_value=application.EmailResult(True, "Mail gönderildi"),
        ) as mocked_send:
            response = self.client.post(
                "/api/forgot-password",
                json={"email": email},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        mocked_send.assert_called_once()
        reset_link_body = mocked_send.call_args.args[2]
        raw_token = reset_link_body.split("reset_token=", 1)[1].splitlines()[0]

        with application.connect() as db:
            reset = db.execute(
                "SELECT * FROM password_resets WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        self.assertIsNotNone(reset)
        self.assertNotEqual(reset["token"], raw_token)
        self.assertEqual(
            reset["token"],
            application.hash_reset_token(raw_token),
        )
        self.assertIsNone(reset["used_at"])

    def test_appointment_email_helper_uses_smtp_service(self):
        appointment = {
            "email": "customer@example.com",
            "first_name": "Elif",
            "appt_date": "2026-06-20",
            "appt_time": "14:30",
            "service": "Aşı",
            "pet_name": "Mavi",
        }
        with patch(
            "app.send_email",
            return_value=application.EmailResult(True, "Mail gönderildi"),
        ) as mocked_send:
            result = application.send_appointment_status_email(
                appointment,
                "confirmed",
            )
        self.assertTrue(result.success)
        mocked_send.assert_called_once()
        self.assertIn("onaylandı", mocked_send.call_args.args[1])

    def test_appointment_update_succeeds_when_mail_fails(self):
        with application.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO appointments
                (first_name, last_name, phone, email, pet_type, pet_name, service,
                 appt_date, appt_time, notes, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    "Mail",
                    "Hatası",
                    "05000000002",
                    "appointment@example.com",
                    "Kedi",
                    "Mavi",
                    "Muayene",
                    "2026-07-01",
                    "09:15",
                    "",
                    "2026-06-14T10:00:00",
                ),
            )
            appointment_id = cursor.lastrowid
            db.commit()

        token = application.create_admin_jwt(999, "test-admin")
        with patch(
            "app.send_appointment_status_email",
            return_value=application.EmailResult(
                False,
                "Mail gönderilemedi",
                "SMTP test hatası",
            ),
        ):
            response = self.client.patch(
                f"/api/admin/appointments/update/{appointment_id}",
                json={"status": "confirmed"},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertFalse(response.get_json()["data"]["mail"]["success"])
        with application.connect() as db:
            appointment = db.execute(
                "SELECT status FROM appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()
        self.assertEqual(appointment["status"], "confirmed")

    def test_order_update_succeeds_when_mail_fails(self):
        with application.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO orders
                (first_name, last_name, phone, email, address, notes, total,
                 status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    "Kargo",
                    "Hatası",
                    "05000000003",
                    "order@example.com",
                    "Samsun",
                    "",
                    250.0,
                    "2026-06-14T10:00:00",
                ),
            )
            order_id = cursor.lastrowid
            db.commit()

        token = application.create_admin_jwt(999, "test-admin")
        with patch(
            "app.send_order_status_email",
            return_value=application.EmailResult(
                False,
                "Mail gönderilemedi",
                "SMTP test hatası",
            ),
        ):
            response = self.client.patch(
                f"/api/admin/orders/update/{order_id}",
                json={"status": "shipped"},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertFalse(response.get_json()["data"]["mail"]["success"])
        with application.connect() as db:
            order = db.execute(
                "SELECT status FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual(order["status"], "shipped")

    def test_member_order_returns_items_after_database_insert(self):
        with application.connect() as db:
            product = db.execute(
                """
                INSERT INTO products (name, category, price, stock, active)
                VALUES (?, ?, ?, ?, 1)
                """,
                ("Sipariş Test Ürünü", "Test", 125.0, 4),
            )
            product_id = product.lastrowid
            db.commit()

        response = self.client.post(
            "/api/orders",
            json={
                "first_name": "Test",
                "last_name": "Müşteri",
                "phone": "05000000004",
                "email": "customer@example.com",
                "address": "Toptepe Mahallesi Test Sokak No 10 Samsun",
                "items": [{"product_id": product_id, "quantity": 2}],
                "card_name": "Test Müşteri",
                "card_number": "4242424242424242",
                "card_expiry": "12/30",
                "card_cvc": "123",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["total"], 250.0)
        self.assertEqual(payload["items"][0]["product_id"], product_id)
        self.assertEqual(payload["items"][0]["quantity"], 2)
        with application.connect() as db:
            product = db.execute(
                "SELECT stock FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        self.assertEqual(product["stock"], 2)


if __name__ == "__main__":
    unittest.main()
