import os
import tempfile
import unittest
from pathlib import Path


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
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{TEST_DB}{suffix}")
            if path.exists():
                path.unlink()

    def test_health_endpoint_reports_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["database_type"], "sqlite")

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


if __name__ == "__main__":
    unittest.main()
