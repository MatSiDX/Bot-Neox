import unittest
from unittest.mock import patch

import web_dashboard


class TicketTranscriptDashboardTests(unittest.TestCase):
    def test_deleted_fine_ticket_is_not_counted_as_open(self):
        records = [
            web_dashboard.normalize_ticket_record({
                "ticket_type": "fine",
                "fine_id": "7",
                "status": "open",
                "is_deleted": True,
                "deleted_at": "2026-06-25T12:00:00Z",
            })
        ]

        summary = web_dashboard.ticket_records_summary(records)

        self.assertEqual(summary["open"], 0)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(summary["fine"], 1)

    def test_string_zero_deleted_flag_does_not_mark_ticket_deleted(self):
        record = web_dashboard.normalize_ticket_record({
            "ticket_type": "fine",
            "fine_id": "8",
            "status": "open",
            "is_deleted": "0",
        })

        self.assertEqual(record["status"], "open")

    def test_ticket_records_page_merges_sqlite_fines_and_filters_by_type(self):
        fine = {
            "id": 10,
            "guild_id": "100",
            "fined_user_id": "200",
            "fined_user_name": "Player",
            "amount": 1500,
            "reason": "Llegada tarde",
            "report_ava": "AVA-10",
            "status": "open",
            "is_deleted": 0,
            "ticket_channel_id": "300",
            "created_at": "2026-06-25T10:00:00Z",
            "closed_at": "",
            "deleted_at": "",
        }

        with patch.object(web_dashboard, "get_guild_ticket_records", return_value=[]), \
             patch.object(web_dashboard.FineService, "get_ticket_records", return_value=[fine]):
            payload = web_dashboard.get_guild_ticket_records_page(
                "100",
                {
                    "page": 1,
                    "page_size": 10,
                    "search": "",
                    "status": "",
                    "record_type": "fine",
                    "date_from": "",
                    "date_to": "",
                },
            )

        self.assertEqual(payload["total_items"], 1)
        self.assertEqual(payload["records"][0]["ticket_type"], "fine")
        self.assertEqual(payload["records"][0]["status"], "open")
        self.assertEqual(payload["records"][0]["fine"]["amount"], 1500)
        self.assertEqual(payload["records"][0]["fine"]["reason"], "Llegada tarde")
        self.assertEqual(payload["summary"]["open"], 1)

    def test_ticket_records_page_deduplicates_fine_and_preserves_transcript(self):
        records = [
            {
                "ticket_type": "fine",
                "fine_id": "10",
                "number": 10,
                "guild_id": "100",
                "channel_id": "300",
                "status": "closed",
                "closed_at": "2026-06-25T11:00:00Z",
                "transcript": [{"content": "Apelacion"}],
            }
        ]
        fine = {
            "id": 10,
            "guild_id": "100",
            "fined_user_id": "200",
            "fined_user_name": "Player",
            "amount": 1500,
            "reason": "Llegada tarde",
            "status": "open",
            "is_deleted": 0,
            "ticket_channel_id": "300",
            "created_at": "2026-06-25T10:00:00Z",
            "closed_at": "",
            "deleted_at": "",
        }

        with patch.object(web_dashboard, "get_guild_ticket_records", return_value=records), \
             patch.object(web_dashboard.FineService, "get_ticket_records", return_value=[fine]):
            payload = web_dashboard.get_guild_ticket_records_page(
                "100",
                {
                    "page": 1,
                    "page_size": 10,
                    "search": "llegada",
                    "status": "",
                    "record_type": "fine",
                    "date_from": "",
                    "date_to": "",
                },
            )

        self.assertEqual(payload["total_items"], 1)
        record = payload["records"][0]
        self.assertEqual(record["status"], "closed")
        self.assertEqual(record["transcript_count"], 1)
        self.assertEqual(record["fine"]["amount"], 1500)
        self.assertEqual(record["fine"]["reason"], "Llegada tarde")

    def test_ticket_records_page_filters_by_panel_ticket_type(self):
        records = [
            {
                "number": 1,
                "guild_id": "100",
                "panel_id": "postulacionava",
                "panel_name": "Postulacionava",
                "channel_id": "301",
                "status": "open",
                "created_at": "2026-06-25T10:00:00Z",
            },
            {
                "number": 2,
                "guild_id": "100",
                "panel_id": "soporte",
                "panel_name": "Soporte",
                "channel_id": "302",
                "status": "open",
                "created_at": "2026-06-25T11:00:00Z",
            },
        ]

        with patch.object(web_dashboard, "get_guild_ticket_records", return_value=records), \
             patch.object(web_dashboard.FineService, "get_ticket_records", return_value=[]):
            payload = web_dashboard.get_guild_ticket_records_page(
                "100",
                {
                    "page": 1,
                    "page_size": 10,
                    "search": "",
                    "status": "",
                    "record_type": "panel:postulacionava",
                    "date_from": "",
                    "date_to": "",
                },
            )

        self.assertEqual(payload["total_items"], 1)
        self.assertEqual(payload["records"][0]["panel_name"], "Postulacionava")

    def test_ticket_records_page_can_sort_oldest_first(self):
        records = [
            {
                "number": 1,
                "guild_id": "100",
                "panel_id": "postulacionava",
                "panel_name": "Postulacionava",
                "channel_id": "301",
                "status": "open",
                "created_at": "2026-06-25T10:00:00Z",
            },
            {
                "number": 2,
                "guild_id": "100",
                "panel_id": "postulacionava",
                "panel_name": "Postulacionava",
                "channel_id": "302",
                "status": "open",
                "created_at": "2026-06-25T11:00:00Z",
            },
        ]

        with patch.object(web_dashboard, "get_guild_ticket_records", return_value=records), \
             patch.object(web_dashboard.FineService, "get_ticket_records", return_value=[]):
            payload = web_dashboard.get_guild_ticket_records_page(
                "100",
                {
                    "page": 1,
                    "page_size": 10,
                    "search": "",
                    "status": "",
                    "record_type": "",
                    "sort": "oldest",
                    "date_from": "",
                    "date_to": "",
                },
            )

        self.assertEqual([item["number"] for item in payload["records"]], [1, 2])

    def test_build_ticket_export_payload_includes_basic_ticket_data(self):
        record = web_dashboard.normalize_ticket_record({
            "number": 12,
            "guild_id": "100",
            "channel_id": "300",
            "channel_name": "ticket-0012",
            "owner_id": "200",
            "owner_name": "Player",
            "panel_name": "Soporte",
            "status": "closed",
            "created_at": "2026-06-25T10:00:00Z",
            "closed_at": "2026-06-25T11:00:00Z",
            "transcript": [
                {
                    "created_at": "25/06/2026 | 10:10",
                    "author_name": "Player",
                    "content": "Necesito ayuda",
                }
            ],
        })

        payload = web_dashboard.build_ticket_export_payload("100", "Servidor Test", record)

        self.assertEqual(payload["guild_id"], "100")
        self.assertEqual(payload["ticket"]["number"], 12)
        self.assertEqual(payload["ticket"]["channel"]["name"], "ticket-0012")
        self.assertEqual(payload["ticket"]["user"]["id"], "200")
        self.assertEqual(payload["ticket"]["status"], "closed")
        self.assertEqual(payload["transcript"]["message_count"], 1)
        self.assertIn("Necesito ayuda", payload["transcript"]["content_text"])

    def test_build_ticket_export_payload_rejects_ticket_without_transcript(self):
        record = web_dashboard.normalize_ticket_record({
            "number": 12,
            "guild_id": "100",
            "channel_id": "300",
            "status": "open",
            "transcript": [],
        })

        with self.assertRaisesRegex(ValueError, "no tiene transcripcion"):
            web_dashboard.build_ticket_export_payload("100", "Servidor Test", record)

    def test_build_ticket_export_payload_supports_fine_ticket(self):
        record = web_dashboard.normalize_ticket_record({
            "ticket_type": "fine",
            "fine_id": "9",
            "number": 9,
            "guild_id": "100",
            "channel_id": "309",
            "channel_name": "multa-0009",
            "owner_id": "209",
            "owner_name": "Player Multado",
            "status": "deleted",
            "deleted_at": "2026-06-25T12:00:00Z",
            "transcript": [
                {
                    "created_at": "25/06/2026 | 12:10",
                    "author_name": "Moderador",
                    "content": "Detalle de la multa",
                }
            ],
        })

        payload = web_dashboard.build_ticket_export_payload("100", "Servidor Test", record)

        self.assertEqual(payload["ticket"]["ticket_type"], "fine")
        self.assertEqual(payload["ticket"]["fine_id"], "9")
        self.assertEqual(payload["ticket"]["type_label"], "Multa")
        self.assertEqual(payload["ticket"]["deleted_at"], "2026-06-25T12:00:00Z")
        self.assertEqual(payload["ticket"]["fine"]["id"], "9")


if __name__ == "__main__":
    unittest.main()
