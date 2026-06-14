import unittest

from services.postgres_adapter import PostgresCursor


class _IterableCursor:
    rowcount = 2

    def __iter__(self):
        return iter([{"id": 1}, {"id": 2}])

    def fetchone(self):
        return {"id": 1}

    def fetchall(self):
        return [{"id": 1}, {"id": 2}]


class PostgresCursorCompatibilityTests(unittest.TestCase):
    def test_cursor_supports_sqlite_style_iteration(self):
        cursor = PostgresCursor(_IterableCursor())
        self.assertEqual([row["id"] for row in cursor], [1, 2])


if __name__ == "__main__":
    unittest.main()
