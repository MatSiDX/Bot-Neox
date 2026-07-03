import json
import unittest

from services.loot_normalization_service import (
    LootNormalizationError,
    LootNormalizationService,
)


class LootNormalizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = LootNormalizationService()

    def test_normalizes_statistics_analysis_csv_and_groups_by_player(self):
        csv_text = "\n".join([
            "timestamp_utc;looted_by__alliance;looted_by__guild;looted_by__name;item_id;item_name;quantity;looted_from__name",
            "2026-06-25T19:51:15Z;;Overprice;Gont8;T4_RUNE;Runa del iniciado;1;Mob",
            "2026-06-25T19:51:16Z;;Overprice;Gont8;T4_RUNE;Runa del iniciado;2;Mob",
            "2026-06-25T19:51:17Z;;Overprice;Other;T5_SOUL;Alma del experto;1;Mob",
        ])

        result = self.service.normalize_csv_text(csv_text, source_name="loot.csv").to_dict()

        self.assertTrue(result["valid"])
        self.assertEqual(result["record_count"], 3)
        self.assertEqual(result["player_count"], 2)
        self.assertEqual(result["quantity"], 4)
        gont = next(player for player in result["players"] if player["player_name"] == "Gont8")
        self.assertEqual(gont["item_count"], 1)
        self.assertEqual(gont["items"][0]["item_unique_name"], "T4_RUNE")
        self.assertEqual(gont["items"][0]["quantity"], 3)
        self.assertEqual(gont["items"][0]["tier"], 4)
        self.assertEqual(gont["items"][0]["stack_mode"], "stacked_quantity")

    def test_normalizes_nested_json_loot_entries(self):
        payload = {
            "entries": [
                {"type": "party_join", "player": "Ignored"},
                {
                    "type": "loot",
                    "loot": {
                        "looted_by": {"id": "player-1", "name": "Neox"},
                        "item": {
                            "id": "T6_MAIN_SWORD@2",
                            "name": "Broadsword",
                            "quantity": 1,
                            "quality": 3,
                        },
                    },
                },
            ]
        }

        result = self.service.normalize_json_text(json.dumps(payload)).to_dict()

        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["skipped_records"], 1)
        record = result["records"][0]
        self.assertEqual(record["player_name"], "Neox")
        self.assertEqual(record["player_id"], "player-1")
        self.assertEqual(record["item_unique_name"], "T6_MAIN_SWORD@2")
        self.assertEqual(record["tier"], 6)
        self.assertEqual(record["enchantment"], 2)
        self.assertEqual(record["quality"], 3)
        self.assertFalse(record["stackable"])

    def test_marks_invalid_records_without_rejecting_valid_rows(self):
        csv_text = "\n".join([
            "player_name,item_id,quantity",
            "Valid,T4_BAG,1",
            ",T5_BAG,1",
            "Invalid,T6_BAG,zero",
        ])

        result = self.service.normalize_csv_text(csv_text).to_dict()

        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["invalid_records"], 2)
        self.assertEqual(
            {issue["code"] for issue in result["issues"]},
            {"missing_player", "invalid_quantity"},
        )

    def test_rejects_payload_without_supported_shape(self):
        with self.assertRaises(LootNormalizationError):
            self.service.normalize_payload({"content": "player,item\nNeox,T4_BAG"})


if __name__ == "__main__":
    unittest.main()
