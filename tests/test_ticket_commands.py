import unittest

from cogs.ticket_runtime import TicketRuntimeCog


class TicketCommandTests(unittest.TestCase):
    def test_close_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.close_ticket_command.name,
            "cerrar-ticket",
        )

    def test_transcript_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.transcript_ticket_command.name,
            "transcribir-ticket",
        )

    def test_closed_controls_include_reopen_button(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        view = cog.closed_controls(123)
        custom_ids = [item.custom_id for item in view.children]

        self.assertIn("ticket_runtime_reopen:123", custom_ids)

    def test_closed_controls_include_transcript_delete_button(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        view = cog.closed_controls(123)
        custom_ids = [item.custom_id for item in view.children]

        self.assertIn("ticket_runtime_transcript_delete:123", custom_ids)

    def test_can_reopen_uses_reopen_roles(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"permissions": {"reopen_roles": ["55"]}}

        class Role:
            id = 55

        class Member:
            roles = [Role()]

            class guild_permissions:
                administrator = False

        self.assertTrue(cog.can_reopen(Member(), panel))

    def test_ticket_role_permissions_use_configured_channel_permissions(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {
            "permissions": {
                "ticket_role_permissions": [
                    {
                        "role_id": "55",
                        "permissions": ["view_channel", "send_messages", "invalid"],
                    }
                ]
            }
        }

        self.assertEqual(
            cog.ticket_role_permissions(panel),
            {55: {"view_channel", "send_messages"}},
        )

    def test_can_close_requires_configured_close_role(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"permissions": {"close_roles": ["55"]}}
        record = {"owner_id": "10", "claimed_by_id": "10"}

        class Role:
            id = 55

        class MemberWithCloseRole:
            id = 99
            roles = [Role()]

            class guild_permissions:
                administrator = False

        class OwnerWithoutCloseRole:
            id = 10
            roles = []

            class guild_permissions:
                administrator = False

        self.assertTrue(cog.can_close(MemberWithCloseRole(), panel, record))
        self.assertFalse(cog.can_close(OwnerWithoutCloseRole(), panel, record))


if __name__ == "__main__":
    unittest.main()
