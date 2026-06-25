import os
import tempfile
import unittest
from unittest.mock import patch

from services.dashboard_action_service import DashboardActionService


class DashboardActionServiceTests(unittest.TestCase):
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
        self.service = DashboardActionService()

    def test_create_and_get_request(self):
        request = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10", "caller_id": "20"},
            requested_by="99",
        )

        loaded = self.service.get_request(request["id"])

        self.assertEqual(loaded["guild_id"], "10")
        self.assertEqual(loaded["action_type"], "publish_report")
        self.assertEqual(loaded["payload"]["caller_id"], "20")
        self.assertEqual(loaded["status"], "pending")
        self.assertEqual(loaded["requested_by"], "99")

    def test_idempotency_key_reuses_existing_request(self):
        first = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
            idempotency_key="guild-10-report-1",
        )
        second = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10", "other": True},
            idempotency_key="guild-10-report-1",
        )

        self.assertEqual(first["id"], second["id"])

    def test_claim_next_request_locks_single_worker(self):
        created = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
        )

        claimed = self.service.claim_next_request("worker-a", action_types=["publish_report"])
        missing = self.service.claim_next_request("worker-b", action_types=["publish_report"])

        self.assertEqual(claimed["id"], created["id"])
        self.assertEqual(claimed["status"], "processing")
        self.assertIsNone(missing)

    def test_fail_request_moves_to_retry_when_budget_allows(self):
        created = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
            max_retries=3,
        )
        self.service.claim_next_request("worker-a", action_types=["publish_report"])

        retried = self.service.fail_request(
            created["id"],
            error="Discord temporalmente no disponible",
            retryable=True,
            retry_delay_seconds=15,
        )

        self.assertEqual(retried["status"], "retry")
        self.assertEqual(retried["retry_count"], 1)
        self.assertTrue(retried["next_retry_at"])
        self.assertEqual(retried["locked_at"], "")

    def test_fail_request_marks_failed_when_retry_budget_is_exhausted(self):
        created = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
            max_retries=1,
        )
        self.service.claim_next_request("worker-a", action_types=["publish_report"])

        failed = self.service.fail_request(
            created["id"],
            error="No encontre la Ava activa.",
            retryable=True,
        )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["retry_count"], 1)
        self.assertTrue(failed["processed_at"])

    def test_complete_request_clears_lock_and_stores_result(self):
        created = self.service.create_request(
            guild_id="10",
            action_type="publish_report",
            payload={"guild_id": "10"},
        )
        self.service.claim_next_request("worker-a", action_types=["publish_report"])

        completed = self.service.complete_request(
            created["id"],
            result={"published": True},
        )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"], {"published": True})
        self.assertEqual(completed["locked_by"], "")
        self.assertTrue(completed["processed_at"])


if __name__ == "__main__":
    unittest.main()
