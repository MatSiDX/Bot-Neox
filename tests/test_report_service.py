import unittest

from services.report_service import ReportFormatService


class ReportFormatServiceExclusionTests(unittest.TestCase):
    def setUp(self):
        self.formatter = ReportFormatService()
        self.slots = [
            {"index": 1, "slot": "MainTank", "user_id": 111},
            {"index": 2, "slot": "Heal", "user_id": 222},
            {"index": 3, "slot": "Dps", "user_id": 333},
        ]

    def test_normalizes_valid_exclusions_once(self):
        exclusions = self.formatter.normalize_split_exclusions(
            [
                {"user_id": "222", "user_name": "Heal One", "reason": "Sin loot", "activity_percentage": "50%"},
                {"user_id": "222", "reason": "Duplicado"},
                {"user_id": "999", "reason": "No pertenece"},
            ],
            self.slots,
        )

        self.assertEqual(
            exclusions,
            [
                {
                    "user_id": 222,
                    "user_name": "Heal One",
                    "slot": "Heal",
                    "reason": "Sin loot",
                    "activity_percentage": 50.0,
                }
            ],
        )

    def test_excluded_player_is_not_in_distribution_and_stays_in_report(self):
        exclusions = self.formatter.normalize_split_exclusions(
            [{"user_id": "222", "reason": "Sin loot"}],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=2,
            split_mode="items_silver",
        )

        distribution = self.formatter.build_distribution(
            self.slots,
            caller_id=111,
            split=split,
            adjustments={},
            exclusions=exclusions,
        )
        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=900_000,
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            adjustments={},
            split=split,
            slots=self.slots,
            exclusions=exclusions,
        )

        self.assertEqual(split["item_per_user"], 450_000)
        self.assertEqual([entry["user_id"] for entry in distribution], [111, 333])
        self.assertIn("> 2.Heal: <@222> Excluido del split: Sin loot", content)
        self.assertIn("## Excluidos del split", content)

    def test_exclusion_activity_percentage_is_rendered_without_fine(self):
        exclusions = self.formatter.normalize_split_exclusions(
            [{"user_id": "222", "activity_percentage": "25"}],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=2,
            split_mode="items_silver",
        )

        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=900_000,
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            adjustments={},
            split=split,
            slots=self.slots,
            exclusions=exclusions,
        )

        self.assertIn("> 2.Heal: <@222> Descuento de actividad -25%", content)
        self.assertIn("- <@222> | Heal | Descuento de actividad | -25%", content)

    def test_activity_discount_pays_remaining_percentage(self):
        exclusions = self.formatter.normalize_split_exclusions(
            [{"user_id": "222", "activity_percentage": "50"}],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=1_000_000,
            mapa=0,
            repa=0,
            participant_count=self.formatter.split_participant_count([111, 222, 333], exclusions),
            split_mode="items_silver",
        )

        distribution = self.formatter.build_distribution(
            self.slots,
            caller_id=111,
            split=split,
            adjustments={},
            exclusions=exclusions,
        )

        self.assertEqual(split["split_participants"], 2.5)
        self.assertEqual(split["item_per_user"], 400_000)
        self.assertEqual(
            [(entry["user_id"], entry["amount"]) for entry in distribution],
            [(111, 400_000), (222, 200_000), (333, 400_000)],
        )

    def test_items_mode_applies_repairs_and_tab_sale(self):
        split = self.formatter.calculate_split(
            silver=0,
            items=1_000_000,
            mapa=0,
            repa=100_000,
            participant_count=2,
            split_mode="items",
            tab_sale_percentage=10,
        )

        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=1_000_000,
            silver=0,
            items=1_000_000,
            mapa=0,
            repa=100_000,
            adjustments={},
            split=split,
            slots=self.slots[:2],
            exclusions=[],
        )

        self.assertEqual(split["item_pool"], 800_000)
        self.assertEqual(split["item_per_user"], 400_000)
        self.assertIn("**Repa:** -100K", content)
        self.assertIn("**Venta de tab:** -10%", content)

    def test_global_split_modifier_changes_pool_before_split(self):
        modifiers = self.formatter.normalize_split_modifiers(
            [
                {"name": "Compra", "operation": "subtract", "amount": "100000", "target_type": "total"},
                {"name": "Bonus", "operation": "add", "amount": "50000", "target_type": "total"},
            ],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode="items",
            split_modifiers=modifiers,
        )
        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=900_000,
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            adjustments={},
            split=split,
            slots=self.slots,
            exclusions=[],
            split_modifiers=modifiers,
        )

        self.assertEqual(split["item_pool"], 850_000)
        self.assertEqual(split["item_per_user"], 283_333)
        self.assertEqual(split["global_modifier_total"], -50_000)
        self.assertIn("**Modificadores:** -50K", content)
        self.assertIn("## Modificadores del split", content)

    def test_player_split_modifier_changes_distribution_only_for_target(self):
        modifiers = self.formatter.normalize_split_modifiers(
            [
                {
                    "name": "Descuento manual",
                    "operation": "subtract",
                    "amount": "25000",
                    "target_type": "player",
                    "user_id": "222",
                }
            ],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode="items",
            split_modifiers=modifiers,
        )
        distribution = self.formatter.build_distribution(
            self.slots,
            caller_id=111,
            split=split,
            adjustments={},
            exclusions=[],
            split_modifiers=modifiers,
        )

        self.assertEqual(split["item_per_user"], 300_000)
        self.assertIn(
            {
                "index": 2,
                "slot": "Heal",
                "user_id": 222,
                "note": "-25.000 Descuento manual",
                "category": "silver",
                "amount": -25_000,
                "is_pp": False,
                "modifier": True,
            },
            distribution,
        )

    def test_build_loan_discount_is_subtracted_only_from_target_player(self):
        discounts = self.formatter.normalize_build_loan_discounts(
            [
                {
                    "user_id": "222",
                    "user_name": "Heal One",
                    "amount": "50k",
                    "reason": "Build healer",
                    "collection_method": "split",
                    "proof_path": "data/fine_proofs/build.png",
                    "proof_name": "build.png",
                },
                {"user_id": "999", "amount": "10k", "reason": "No pertenece", "collection_method": "split"},
                {"user_id": "333", "amount": "0", "reason": "Monto invalido", "collection_method": "split"},
            ],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode="items",
        )
        distribution = self.formatter.build_distribution(
            self.slots,
            caller_id=111,
            split=split,
            adjustments={},
            exclusions=[],
            split_modifiers=[],
            build_loan_discounts=discounts,
        )

        self.assertEqual(
            discounts,
            [
                {
                    "user_id": 222,
                    "user_name": "Heal One",
                    "slot": "Heal",
                    "amount": 50_000,
                    "reason": "Build healer",
                    "collection_method": "split",
                    "proof_path": "data/fine_proofs/build.png",
                    "proof_name": "build.png",
                }
            ],
        )
        self.assertEqual(
            [(entry["user_id"], entry["amount"]) for entry in distribution],
            [(111, 300_000), (222, 300_000), (222, -50_000), (333, 300_000)],
        )

    def test_build_loan_discount_is_rendered_in_report_content(self):
        discounts = self.formatter.normalize_build_loan_discounts(
            [{"user_id": "222", "amount": "50000", "reason": "Build healer", "collection_method": "split"}],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode="items",
        )
        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=900_000,
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            adjustments={},
            split=split,
            slots=self.slots,
            exclusions=[],
            split_modifiers=[],
            build_loan_discounts=discounts,
        )

        self.assertIn("> 2.Heal: <@222> -50.000 préstamo de build", content)
        self.assertIn("## Préstamos de build", content)
        self.assertIn("<@222> | 50.000 | se le resta del split: Build healer", content)



    def test_build_loan_balance_and_paid_now_methods(self):
        discounts = self.formatter.normalize_build_loan_discounts(
            [
                {"user_id": "222", "amount": "50k", "reason": "Balance", "collection_method": "balance"},
                {"user_id": "333", "amount": "", "reason": "Pago", "collection_method": "paid_now"},
            ],
            self.slots,
        )
        split = self.formatter.calculate_split(
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            participant_count=3,
            split_mode="items",
        )
        distribution = self.formatter.build_distribution(
            self.slots,
            caller_id=111,
            split=split,
            adjustments={},
            exclusions=[],
            split_modifiers=[],
            build_loan_discounts=discounts,
        )

        self.assertEqual([entry["collection_method"] for entry in discounts], ["balance", "paid_now"])
        self.assertEqual(discounts[1]["amount"], 0)
        self.assertEqual(
            [(entry["user_id"], entry["amount"], entry.get("collection_method")) for entry in distribution],
            [(111, 300_000, None), (222, 300_000, None), (222, -50_000, "balance"), (333, 300_000, None)],
        )

        content = self.formatter.build_report_content(
            title="Ava 1",
            caller_id=111,
            estimated=900_000,
            silver=0,
            items=900_000,
            mapa=0,
            repa=0,
            adjustments={},
            split=split,
            slots=self.slots,
            exclusions=[],
            split_modifiers=[],
            build_loan_discounts=discounts,
        )
        self.assertIn("<@333> | pago al momento: Pago", content)

if __name__ == "__main__":
    unittest.main()
