import asyncio
import inspect
import os
import tempfile
import unittest
from types import SimpleNamespace

try:
    from views.avalonian_ping_view import AvalonSignupView
except ModuleNotFoundError:
    AvalonSignupView = None


@unittest.skipUnless(AvalonSignupView is not None, "discord.py no esta instalado en este entorno")
class AvalonianSignupSlotTests(unittest.TestCase):
    def build_view(self, slots, persisted_states):
        return AvalonSignupView(
            numero_ava=42,
            join_command="/join Caller",
            caller=None,
            caller_id=100,
            caller_name="Caller",
            guild_id=200,
            template={
                "key": "test",
                "name": "Test",
                "title": "Ava {numero}",
                "caller_slot": "MainTank",
                "roles": ["MainTank", "DPS", "DPS", "DPS", "Heal"],
                "slot_format": "> **{index}.{slot}:** {user}",
                "content": "{slots}\n\nCupos: {occupied}/{total}{status}",
                "join_command": "/join {caller}",
            },
            slots=slots,
            persist_callback=persisted_states.append,
        )

    def test_remove_user_clears_all_duplicate_dps_slots(self):
        persisted_states = []
        view = self.build_view(
            {
                "MainTank": 100,
                "DPS": "300",
                "DPS#2": 301,
                "DPS#3": 300,
                "Heal": 302,
            },
            persisted_states,
        )

        removed_slot = view.remove_user(300)

        self.assertEqual(removed_slot, "DPS")
        self.assertIsNone(view.slots["DPS"])
        self.assertEqual(view.slots["DPS#2"], 301)
        self.assertIsNone(view.slots["DPS#3"])
        self.assertNotIn("<@300>", view.build_content())
        self.assertEqual(persisted_states[-1]["slots"]["DPS"], None)
        self.assertEqual(persisted_states[-1]["slots"]["DPS#3"], None)

    def test_empty_dps_slot_does_not_render_other_dps_mentions(self):
        view = self.build_view(
            {
                "MainTank": 100,
                "DPS": 300,
                "DPS#2": 301,
                "DPS#3": None,
                "Heal": 302,
            },
            [],
        )

        content = view.build_content()

        self.assertIn("> **2.DPS:** <@300>", content)
        self.assertIn("> **3.DPS:** <@301>", content)
        self.assertIn("> **4.DPS:** ", content)
        self.assertNotIn("> **4.DPS:** <@300>", content)
        self.assertNotIn("> **4.DPS:** <@301>", content)

    def test_remove_user_does_not_remove_caller_slot(self):
        persisted_states = []
        view = self.build_view(
            {
                "MainTank": 100,
                "DPS": 100,
                "DPS#2": 301,
                "DPS#3": None,
                "Heal": 302,
            },
            persisted_states,
        )

        removed_slot = view.remove_user(100)

        self.assertEqual(removed_slot, "DPS")
        self.assertEqual(view.slots["MainTank"], 100)
        self.assertIsNone(view.slots["DPS"])

    def test_cancel_ping_marks_inactive_and_removes_controls(self):
        persisted_states = []
        inactive_states = []
        closed_keys = []
        view = self.build_view(
            {
                "MainTank": 100,
                "DPS": None,
                "DPS#2": None,
                "DPS#3": None,
                "Heal": None,
            },
            persisted_states,
        )
        view.deactivate_persisted_callback = (
            lambda guild_id, caller_id, numero_ava, status: inactive_states.append(
                (guild_id, caller_id, numero_ava, status)
            )
        )
        view.close_callback = (
            lambda guild_id, caller_id, numero_ava: closed_keys.append(
                (guild_id, caller_id, numero_ava)
            )
        )

        asyncio.run(view.cancel_ping())

        self.assertTrue(view.cancelled)
        self.assertEqual(len(view.children), 0)
        self.assertIn("Cancelada", view.build_content())
        self.assertEqual(inactive_states[-1], (200, 100, 42, "cancelled"))
        self.assertEqual(closed_keys[-1], (200, 100, 42))
        self.assertTrue(persisted_states[-1]["cancelled"])

    def test_build_loan_proofs_are_sent_to_evaluation_target(self):
        class FakeTarget:
            def __init__(self):
                self.sent = []

            async def send(self, content, *, file=None):
                self.sent.append((content, file.filename if file else ""))

        view = self.build_view({"MainTank": 100}, [])
        target = FakeTarget()
        fd, proof_path = tempfile.mkstemp(suffix=".png")
        try:
            with os.fdopen(fd, "wb") as proof:
                proof.write(b"proof")
            asyncio.run(
                view.send_build_loan_proofs_to_thread(
                    target,
                    [
                        {
                            "proof_path": proof_path,
                            "proof_name": "wheel.png",
                        },
                        {
                            "proof_path": "",
                            "proof_name": "missing.png",
                        },
                    ],
                )
            )
        finally:
            if os.path.exists(proof_path):
                os.remove(proof_path)

        self.assertEqual(
            target.sent,
            [("Imagen adjunta del prestamo de guild.", "wheel.png")],
        )

    def test_publish_report_accepts_chest_table_id_from_dashboard(self):
        signature = inspect.signature(AvalonSignupView.publish_report)

        self.assertIn("chest_table_id", signature.parameters)

    def test_report_payload_preserves_chest_table_id(self):
        view = self.build_view({"MainTank": 100}, [])

        report_data = view.build_report_payload(
            caller=SimpleNamespace(id=100, display_name="Caller"),
            estimated="100000",
            silver_text="100000",
            items_text="0",
            costs_text="",
            adjustments_text="",
            chest_table_id="123",
        )

        self.assertEqual(report_data["chest_table_id"], "123")


if __name__ == "__main__":
    unittest.main()
