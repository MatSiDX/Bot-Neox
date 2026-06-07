import unittest

from views.avalonian_ping_view import (
    REPORT_SPLIT_BOTH,
    REPORT_SPLIT_ITEMS,
    REPORT_SPLIT_SILVER,
    AvalonSignupView,
)


class ReportSplitTests(unittest.TestCase):
    def setUp(self):
        self.view = AvalonSignupView.__new__(AvalonSignupView)

    def test_items_mode_combines_net_value_into_items(self):
        split = self.view.calculate_report_split(
            silver=600_000,
            items=1_000_000,
            mapa=100_000,
            repa=50_000,
            participant_count=5,
            split_mode=REPORT_SPLIT_ITEMS,
        )

        self.assertEqual(split["item_pool"], 1_450_000)
        self.assertEqual(split["silver_pool"], 0)
        self.assertEqual(split["item_per_user"], 290_000)
        self.assertEqual(split["silver_per_user"], 0)

    def test_silver_mode_combines_net_value_into_silver(self):
        split = self.view.calculate_report_split(
            silver=600_000,
            items=1_000_000,
            mapa=100_000,
            repa=50_000,
            participant_count=5,
            split_mode=REPORT_SPLIT_SILVER,
        )

        self.assertEqual(split["item_pool"], 0)
        self.assertEqual(split["silver_pool"], 1_450_000)
        self.assertEqual(split["item_per_user"], 0)
        self.assertEqual(split["silver_per_user"], 290_000)

    def test_both_mode_keeps_categories_separate(self):
        split = self.view.calculate_report_split(
            silver=600_000,
            items=1_000_000,
            mapa=100_000,
            repa=50_000,
            participant_count=5,
            split_mode=REPORT_SPLIT_BOTH,
        )

        self.assertEqual(split["item_pool"], 1_000_000)
        self.assertEqual(split["silver_pool"], 450_000)
        self.assertEqual(split["item_per_user"], 200_000)
        self.assertEqual(split["silver_per_user"], 90_000)

    def test_costs_never_make_silver_negative(self):
        split = self.view.calculate_report_split(
            silver=100_000,
            items=0,
            mapa=150_000,
            repa=50_000,
            participant_count=4,
            split_mode=REPORT_SPLIT_BOTH,
        )

        self.assertEqual(split["silver_pool"], 0)
        self.assertEqual(split["silver_per_user"], 0)

    def test_both_mode_creates_one_entry_per_category(self):
        self.view.iter_slots = lambda: [(1, "Dps1", "Dps", 123)]
        split = self.view.calculate_report_split(
            silver=500_000,
            items=1_000_000,
            mapa=0,
            repa=0,
            participant_count=1,
            split_mode=REPORT_SPLIT_BOTH,
        )

        distribution = self.view.build_report_distribution(split, {})

        self.assertEqual(
            [(entry["category"], entry["amount"]) for entry in distribution],
            [("items", 1_000_000), ("silver", 500_000)],
        )

    def test_pp_in_items_mode_uses_available_silver(self):
        self.view.iter_slots = lambda: [(1, "Heal", "Heal", 456)]
        split = self.view.calculate_report_split(
            silver=300_000,
            items=0,
            mapa=0,
            repa=0,
            participant_count=1,
            split_mode=REPORT_SPLIT_ITEMS,
        )

        distribution = self.view.build_report_distribution(split, {"Heal": "PP"})
        _, available, required, difference = self.view.evaluate_pp_distribution(split, distribution)

        self.assertEqual(distribution[0]["category"], "silver")
        self.assertEqual(available, 300_000)
        self.assertEqual(required, 300_000)
        self.assertEqual(difference, 0)

    def test_both_mode_with_tab_sale_turns_everything_into_silver(self):
        split = self.view.calculate_report_split(
            silver=5_000_000,
            items=10_000_000,
            mapa=500_000,
            repa=250_000,
            participant_count=5,
            split_mode=REPORT_SPLIT_BOTH,
            caller_percentage=10,
            looter_payment=1_000_000,
            tab_sale_percentage=15,
        )

        self.assertEqual(split["mode"], REPORT_SPLIT_SILVER)
        self.assertEqual(split["item_pool"], 0)
        self.assertEqual(split["silver_pool"], 10_750_000)
        self.assertEqual(split["silver_per_user"], 2_150_000)

    def test_silver_mode_pp_uses_full_silver_pool(self):
        self.view.iter_slots = lambda: [(1, "Heal", "Heal", 456)]
        split = self.view.calculate_report_split(
            silver=300_000,
            items=700_000,
            mapa=0,
            repa=0,
            participant_count=1,
            split_mode=REPORT_SPLIT_SILVER,
        )

        distribution = self.view.build_report_distribution(split, {"Heal": "PP"})
        _, available, required, difference = self.view.evaluate_pp_distribution(split, distribution)

        self.assertEqual(available, 1_000_000)
        self.assertEqual(required, 1_000_000)
        self.assertEqual(difference, 0)

    def test_tab_sale_report_shows_only_silver_mode(self):
        self.view.title = "Ava 1"
        self.view.iter_slots = lambda: [(1, "Heal", "Heal", 456)]
        self.view.caller_id = 456
        split = self.view.calculate_report_split(
            silver=5_000_000,
            items=10_000_000,
            mapa=500_000,
            repa=250_000,
            participant_count=1,
            split_mode=REPORT_SPLIT_BOTH,
            caller_percentage=10,
            looter_payment=1_000_000,
            tab_sale_percentage=15,
        )

        content = self.view.build_report_content(
            estimated="15m",
            silver=5_000_000,
            items=10_000_000,
            mapa=500_000,
            repa=250_000,
            adjustments={},
            split=split,
        )

        self.assertIn("**Modo de reparto:** Solo silver", content)
        self.assertIn("# 10.750.000 Silver C/U", content)
        self.assertNotIn("Items C/U", content)

    def test_looter_payment_excludes_selected_member_from_party_split(self):
        self.view.iter_slots = lambda: [
            (1, "MainTank", "MainTank", 111),
            (2, "Heal", "Heal", 222),
            (3, "Dps", "Dps", 333),
        ]
        self.view.caller_id = 111
        split = self.view.calculate_report_split(
            silver=3_000_000,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode=REPORT_SPLIT_BOTH,
            looter_payment=1_000_000,
            looter_user_id=222,
        )

        distribution = self.view.build_report_distribution(split, {})

        self.assertEqual(split["item_per_user"], 450_000)
        self.assertEqual(split["silver_per_user"], 1_000_000)
        self.assertEqual(
            [(entry["user_id"], entry["category"], entry["amount"]) for entry in distribution],
            [
                (111, "items", 450_000),
                (111, "silver", 1_000_000),
                (222, "silver", 1_000_000),
                (333, "items", 450_000),
                (333, "silver", 1_000_000),
            ],
        )

    def test_caller_bonus_is_added_to_distribution(self):
        self.view.iter_slots = lambda: [
            (1, "MainTank", "MainTank", 111),
            (2, "Heal", "Heal", 222),
        ]
        self.view.caller_id = 111
        split = self.view.calculate_report_split(
            silver=2_000_000,
            items=0,
            mapa=0,
            repa=0,
            participant_count=2,
            split_mode=REPORT_SPLIT_BOTH,
            caller_percentage=10,
        )

        distribution = self.view.build_report_distribution(split, {})

        self.assertEqual(
            [(entry["user_id"], entry["category"], entry["amount"], entry["note"]) for entry in distribution],
            [
                (111, "silver", 900_000, ""),
                (111, "silver", 200_000, "Caller"),
                (222, "silver", 900_000, ""),
            ],
        )

    def test_final_report_moves_caller_and_looter_amounts_to_player_lines(self):
        self.view.title = "Ava 1"
        self.view.caller_id = 111
        self.view.iter_slots = lambda: [
            (1, "MainTank", "MainTank", 111),
            (10, "Looter scout", "Looter scout", 999),
        ]
        split = self.view.calculate_report_split(
            silver=20_000_000,
            items=80_000_000,
            mapa=2_000_000,
            repa=200_000,
            participant_count=2,
            split_mode=REPORT_SPLIT_BOTH,
            caller_percentage=10,
            looter_payment=5_000_000,
            looter_user_id=999,
        )

        content = self.view.build_report_content(
            estimated="100m",
            silver=20_000_000,
            items=80_000_000,
            mapa=2_000_000,
            repa=200_000,
            adjustments={},
            split=split,
        )

        self.assertNotIn("**Caller (10%):**", content)
        self.assertNotIn("**Pago looter:**", content)
        self.assertIn("> 1.MainTank: <@111> + 2.000.000", content)
        self.assertIn("> 10.Looter scout: <@999> Looter +5.000.000", content)


if __name__ == "__main__":
    unittest.main()
