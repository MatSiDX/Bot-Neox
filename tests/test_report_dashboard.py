import unittest

import discord

from views.avalonian_ping_view import AvalonSignupView


class ReportDashboardTests(unittest.TestCase):
    def test_finalized_report_button_links_to_dashboard(self):
        view = AvalonSignupView(
            numero_ava=27,
            join_command="/join Neox",
            caller=None,
            caller_id=123,
            caller_name="Neox",
            guild_id=456,
            finalized=True,
        )

        button = next(item for item in view.children if item.label == "Enviar informe")

        self.assertEqual(button.style, discord.ButtonStyle.link)
        self.assertIn("section=report-calculator", button.url)
        self.assertIn("guild_id=456", button.url)
        self.assertIn("caller_id=123", button.url)
        self.assertIn("ava=27", button.url)


if __name__ == "__main__":
    unittest.main()
