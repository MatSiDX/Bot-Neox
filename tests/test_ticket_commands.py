import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

try:
    from cogs.ticket_runtime import TicketRuntimeCog
except ModuleNotFoundError:
    TicketRuntimeCog = None


class TicketCommandTests(unittest.IsolatedAsyncioTestCase):
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

    def test_reopen_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.reopen_ticket_command.name,
            "reabrir-ticket",
        )

    def test_delete_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.delete_ticket_command.name,
            "eliminar-ticket",
        )

    def test_transcript_delete_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.transcript_delete_ticket_command.name,
            "eliminar-y-transcribir-ticket",
        )

    def test_ticket_command_names_do_not_conflict(self):
        names = {
            TicketRuntimeCog.close_ticket_command.name,
            TicketRuntimeCog.transcript_ticket_command.name,
            TicketRuntimeCog.reopen_ticket_command.name,
            TicketRuntimeCog.delete_ticket_command.name,
            TicketRuntimeCog.transcript_delete_ticket_command.name,
        }

        self.assertEqual(len(names), 5)

    def test_transcript_delete_component_is_checked_before_transcript(self):
        source = TicketRuntimeCog.on_interaction.__code__.co_consts
        constants = [value for value in source if isinstance(value, str)]

        self.assertLess(
            constants.index("ticket_runtime_transcript_delete:"),
            constants.index("ticket_runtime_transcript:"),
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

    def test_administrator_role_can_use_ticket_actions(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)

        class RolePermissions:
            administrator = True

        class Role:
            id = 55
            permissions = RolePermissions()

        class Member:
            roles = [Role()]

            class guild_permissions:
                administrator = False

        self.assertTrue(cog.can_delete(Member(), {"permissions": {}}))

    def test_bot_ticket_permission_can_use_ticket_actions(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.permission_service = Mock()
        cog.permission_service.can_manage_tickets.return_value = True
        panel = {"permissions": {"close_roles": ["55"]}}
        record = {"owner_id": "10", "claimed_by_id": ""}
        member = SimpleNamespace(
            id=99,
            guild=SimpleNamespace(id=10),
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )

        self.assertTrue(cog.can_close(member, panel, record))
        cog.permission_service.can_manage_tickets.assert_called_once_with(10, member)

    def test_bot_ticket_permission_works_without_panel(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.permission_service = Mock()
        cog.permission_service.can_manage_tickets.return_value = True
        member = SimpleNamespace(
            id=99,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )

        self.assertTrue(cog.can_close(member, None, {"status": "open"}, guild_id=10))
        cog.permission_service.can_manage_tickets.assert_called_once_with(10, member)

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

    async def test_delete_ticket_requires_closed_ticket(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.get_record = Mock(return_value=({}, {"status": "open", "panel_id": "panel-1"}))
        cog.find_panel = Mock(return_value={"permissions": {}})
        cog.can_delete = Mock(return_value=True)
        cog.save_records = Mock()
        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            user=SimpleNamespace(),
            response=SimpleNamespace(send_message=AsyncMock()),
            channel=SimpleNamespace(delete=AsyncMock()),
        )

        await cog.delete_ticket(interaction, 123)

        interaction.response.send_message.assert_awaited_once_with(
            "Primero cierra el ticket antes de eliminarlo.",
            ephemeral=True,
        )
        cog.save_records.assert_not_called()
        interaction.channel.delete.assert_not_called()

    async def test_close_ticket_prompt_allows_bot_permission_when_panel_is_missing(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.permission_service = Mock()
        cog.permission_service.can_manage_tickets.return_value = True
        cog.get_record = Mock(return_value=({}, {"status": "open", "panel_id": "missing-panel"}))
        cog.find_panel = Mock(return_value=None)
        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            user=SimpleNamespace(
                id=99,
                roles=[],
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            response=SimpleNamespace(send_message=AsyncMock()),
        )

        await cog.close_ticket_prompt(interaction, 123)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.await_args
        self.assertEqual(args[0], "Confirma que quieres cerrar este ticket.")
        self.assertIn("view", kwargs)
        self.assertTrue(kwargs["ephemeral"])


if __name__ == "__main__":
    unittest.main()
