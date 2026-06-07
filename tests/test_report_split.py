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
        _, available, required, difference = self.view.evaluate_pp_distribution(
            300_000,
            0,
            0,
            distribution,
        )

        self.assertEqual(distribution[0]["category"], "silver")
        self.assertEqual(available, 300_000)
        self.assertEqual(required, 300_000)
        self.assertEqual(difference, 0)


if __name__ == "__main__":
    unittest.main()
