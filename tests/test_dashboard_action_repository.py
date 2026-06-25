import os
import tempfile
import unittest
from unittest.mock import patch

from repositories.dashboard_action_request_repository import DashboardActionRequestRepository


class DashboardActionRequestRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = os.path.join(self.temp_dir.name, "actions.sqlite3")
        patches = [
            patch("repositories.database.DATA_DIR", self.temp_dir.name),
            patch("repositories.database.DATABASE_FILE", self.database_file),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = DashboardActionRequestRepository()

    def test_list_requests_filters_by_status_and_action_type(self):
        first = self.repo.create(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
        )
        second = self.repo.create(
            guild_id="10",
            action_type="publish_ticket_panel",
            payload={"guild_id": "10"},
        )

        self.repo.mark_completed(first["id"], result={"ok": True})

        items = self.repo.list_requests(
            statuses=["completed"],
            action_types=["publish_report"],
        )

        self.assertEqual([item["id"] for item in items], [first["id"]])
        self.assertNotEqual(second["id"], first["id"])

    def test_mark_retry_updates_retry_metadata(self):
        created = self.repo.create(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
            max_retries=3,
        )

        updated = self.repo.mark_retry(
            created["id"],
            error="timeout",
            result={"attempt": 1},
            retry_delay_seconds=5,
        )

        self.assertEqual(updated["status"], "retry")
        self.assertEqual(updated["retry_count"], 1)
        self.assertEqual(updated["result"], {"attempt": 1})
        self.assertTrue(updated["next_retry_at"])


if __name__ == "__main__":
    unittest.main()
