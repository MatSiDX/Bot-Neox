import unittest
from unittest.mock import patch

try:
    import web_dashboard
except ModuleNotFoundError:
    web_dashboard = None


@unittest.skipUnless(web_dashboard is not None, "discord.py no esta instalado en este entorno")
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

    def test_soft_deletes_fine_ticket_without_removing_transcript(self):
        storage = {
            "10": [
                {
                    "ticket_type": "fine",
                    "fine_id": "7",
                    "number": 7,
                    "channel_id": "70",
                    "status": "closed",
                    "transcript": [{"content": "Prueba"}],
                }
            ]
        }
        deleted_fine = {
            "id": 7,
            "guild_id": "10",
            "fined_user_id": "99",
            "fined_user_name": "Player",
            "amount": 1000,
            "reason": "Test",
            "status": "open",
            "is_deleted": 1,
            "ticket_channel_id": "70",
            "deleted_at": "2026-06-25T12:00:00Z",
        }

        class Repo:
            def soft_delete(self, fine_id):
                self.fine_id = fine_id
                return deleted_fine

        repo = Repo()

        def mutate_records(path, fallback, callback):
            callback(storage)

        with (
            patch.object(web_dashboard, "get_ticket_record", return_value=storage["10"][0]),
            patch.object(web_dashboard, "FineRepository", return_value=repo),
            patch.object(web_dashboard, "mutate_json_file_safe", side_effect=mutate_records),
            patch.object(web_dashboard.shutil, "rmtree") as remove_media,
        ):
            removed = web_dashboard.delete_guild_ticket_record("10", "70")

        self.assertTrue(removed)
        self.assertEqual(repo.fine_id, 7)
        self.assertEqual(len(storage["10"]), 1)
        self.assertEqual(storage["10"][0]["status"], "deleted")
        self.assertEqual(storage["10"][0]["fine"]["amount"], 1000)
        self.assertEqual(storage["10"][0]["transcript"], [{"content": "Prueba"}])
        remove_media.assert_not_called()


if __name__ == "__main__":
    unittest.main()
