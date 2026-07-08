import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from repositories.database import init_database
from repositories.fine_repository import FineRepository


class FineSoftDeleteTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

        @contextmanager
        def shared_connection():
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

        patches = [
            patch("repositories.database.get_connection", shared_connection),
            patch("repositories.fine_repository.get_connection", shared_connection),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.addCleanup(self.connection.close)
        init_database()
        self.repo = FineRepository()

    def create_fine(self):
        return self.repo.create(
            {
                "guild_id": "10",
                "guild_name": "Guild",
                "report_ava": "AVA-1",
                "fined_user_id": "99",
                "fined_user_name": "Player",
                "amount": 1000,
                "reason": "Test",
                "ticket_channel_id": "123",
            }
        )

    def test_soft_delete_keeps_fine_history_and_removes_from_open_queries(self):
        fine = self.create_fine()

        deleted = self.repo.soft_delete(fine["id"])

        self.assertIsNotNone(deleted)
        self.assertEqual(deleted["id"], fine["id"])
        self.assertEqual(deleted["status"], "open")
        self.assertEqual(deleted["is_deleted"], 1)
        self.assertTrue(deleted["deleted_at"])
        self.assertEqual(self.repo.get(fine["id"])["is_deleted"], 1)
        self.assertEqual(self.repo.list_open(), [])
        self.assertEqual(self.repo.list_unpaid_by_user("10", "99"), [])

    def test_soft_delete_returns_none_when_fine_does_not_exist(self):
        self.assertIsNone(self.repo.soft_delete(999))

    def test_deleted_filter_returns_historical_fines(self):
        fine = self.create_fine()
        self.repo.soft_delete(fine["id"])

        page = self.repo.list_by_guild_page("10", status="deleted")

        self.assertEqual(page["total_items"], 1)
        self.assertEqual(page["items"][0]["id"], fine["id"])

    def test_init_database_adds_soft_delete_columns_to_existing_fines_table(self):
        self.connection.execute("DROP TABLE economy_fines")
        self.connection.execute(
            """
            CREATE TABLE economy_fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                report_ava TEXT NOT NULL DEFAULT '',
                fined_user_id TEXT NOT NULL,
                fined_user_name TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                proof_path TEXT NOT NULL DEFAULT '',
                proof_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                blocked_role_id TEXT NOT NULL DEFAULT '',
                resolver_role_id TEXT NOT NULL DEFAULT '',
                ticket_channel_id TEXT NOT NULL DEFAULT '',
                ticket_message_id TEXT NOT NULL DEFAULT '',
                announcement_channel_id TEXT NOT NULL DEFAULT '',
                announcement_message_id TEXT NOT NULL DEFAULT '',
                created_by_id TEXT NOT NULL DEFAULT '',
                created_by_name TEXT NOT NULL DEFAULT '',
                paid_by_id TEXT NOT NULL DEFAULT '',
                paid_by_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                paid_at TEXT NOT NULL DEFAULT '',
                closed_at TEXT NOT NULL DEFAULT ''
            )
            """
        )

        init_database()

        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(economy_fines)").fetchall()
        }
        self.assertIn("is_deleted", columns)
        self.assertIn("deleted_at", columns)


if __name__ == "__main__":
    unittest.main()
