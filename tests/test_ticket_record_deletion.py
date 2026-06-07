import unittest
from unittest.mock import patch

import web_dashboard


class TicketRecordDeletionTests(unittest.TestCase):
    def run_delete(self, storage, record_id):
        def mutate_records(path, fallback, callback):
            callback(storage)

        with (
            patch.object(
                web_dashboard,
                "mutate_json_file_safe",
                side_effect=mutate_records,
            ),
            patch.object(web_dashboard.shutil, "rmtree") as remove_media,
        ):
            removed = web_dashboard.delete_guild_ticket_record("10", record_id)
        return removed, remove_media

    def test_removes_closed_ticket_and_media(self):
        storage = {
            "10": [
                {
                    "number": 1,
                    "channel_id": "20",
                    "status": "closed",
                    "transcript": [{"content": "Mensaje"}],
                },
                {
                    "number": 2,
                    "channel_id": "21",
                    "status": "closed",
                    "transcript": [],
                },
            ]
        }

        removed, remove_media = self.run_delete(storage, "20")

        self.assertTrue(removed)
        self.assertEqual([record["channel_id"] for record in storage["10"]], ["21"])
        remove_media.assert_called_once()

    def test_removes_deleted_ticket_without_transcript(self):
        storage = {
            "10": [
                {
                    "number": 1,
                    "channel_id": "20",
                    "status": "deleted",
                    "transcript": [],
                }
            ]
        }

        removed, remove_media = self.run_delete(storage, "20")

        self.assertTrue(removed)
        self.assertNotIn("10", storage)
        remove_media.assert_called_once()

    def test_does_not_remove_open_ticket(self):
        storage = {
            "10": [
                {
                    "number": 1,
                    "channel_id": "20",
                    "status": "open",
                }
            ]
        }

        removed, remove_media = self.run_delete(storage, "20")

        self.assertFalse(removed)
        self.assertEqual(len(storage["10"]), 1)
        remove_media.assert_not_called()


if __name__ == "__main__":
    unittest.main()
