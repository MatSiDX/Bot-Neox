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

    def test_add_member_ticket_command_is_registered(self):
        self.assertEqual(
            TicketRuntimeCog.add_member_ticket_command.name,
            "agregar-a-ticket",
        )

    def test_ticket_command_names_do_not_conflict(self):
        names = {
            TicketRuntimeCog.close_ticket_command.name,
            TicketRuntimeCog.add_member_ticket_command.name,
            TicketRuntimeCog.transcript_ticket_command.name,
            TicketRuntimeCog.reopen_ticket_command.name,
            TicketRuntimeCog.delete_ticket_command.name,
            TicketRuntimeCog.transcript_delete_ticket_command.name,
        }

        self.assertEqual(len(names), 6)

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

    def test_ticket_controls_do_not_include_add_member_button(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        view = cog.ticket_controls(123)
        custom_ids = [item.custom_id for item in view.children]

        self.assertNotIn("ticket_runtime_add_member:123", custom_ids)

    def test_select_panels_number_tickets_by_option(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"id": "panel-1", "mode": "select"}

        scope = cog.ticket_number_scope(panel, "option-a")

        self.assertEqual(scope, "option-a")
        self.assertTrue(cog.record_matches_number_scope({"panel_id": "panel-1", "option_id": "option-a"}, "panel-1", scope))
        self.assertFalse(cog.record_matches_number_scope({"panel_id": "panel-1", "option_id": "option-b"}, "panel-1", scope))

    def test_button_panels_keep_panel_wide_numbering(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"id": "panel-1", "mode": "buttons"}

        scope = cog.ticket_number_scope(panel, "option-a")

        self.assertEqual(scope, "")
        self.assertTrue(cog.record_matches_number_scope({"panel_id": "panel-1", "option_id": "option-b"}, "panel-1", scope))

    def test_can_add_member_uses_add_member_roles(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"permissions": {"add_member_roles": ["55"]}}

        class Role:
            id = 55

        class Member:
            roles = [Role()]

            class guild_permissions:
                administrator = False

        self.assertTrue(cog.can_add_member(Member(), panel))

    def test_can_add_member_uses_configured_user_ids(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {"permissions": {"add_member_user_ids": ["99"]}}
        member = SimpleNamespace(
            id=99,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )

        self.assertTrue(cog.can_add_member(member, panel))

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

    def test_fine_ticket_is_resolved_from_fine_channel(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        records = []
        data = {"10": records}
        cog.guild_records = Mock(return_value=(data, records))
        cog.save_records = Mock()
        cog.fine_repo = Mock()
        cog.fine_repo.get_by_ticket_channel.return_value = {
            "id": 7,
            "guild_id": "10",
            "status": "open",
            "ticket_channel_id": "123",
            "fined_user_id": "99",
            "fined_user_name": "Player",
            "resolver_role_id": "55",
            "created_at": "2026-06-24T00:00:00Z",
            "closed_at": "",
        }

        loaded_data, record = cog.get_record(10, 123)

        self.assertIs(loaded_data, data)
        self.assertEqual(record["ticket_type"], "fine")
        self.assertEqual(record["fine_id"], "7")
        self.assertEqual(record["channel_id"], "123")
        self.assertEqual(record["status"], "open")
        self.assertEqual(records, [record])
        cog.save_records.assert_called_once_with(data)
        cog.fine_repo.get_by_ticket_channel.assert_called_once_with(10, 123)

    async def test_close_rename_uses_ticket_number_and_stores_original_name(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123, name="ticket-0025", edit=AsyncMock())
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(channels=[channel]),
        )
        record = {"number": 25, "channel_name": "ticket-0025"}

        changed = await cog.rename_ticket_channel(interaction, record, closed=True)

        self.assertTrue(changed)
        self.assertEqual(record["original_channel_name"], "ticket-0025")
        self.assertEqual(record["channel_name"], "cerrado-0025")
        channel.edit.assert_awaited_once_with(name="cerrado-0025", reason="Ticket cerrado")

    async def test_close_rename_pads_ticket_number_to_four_digits(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123, name="ticket-0155", edit=AsyncMock())
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(channels=[channel]),
        )
        record = {"number": 155, "channel_name": "ticket-0155"}

        changed = await cog.rename_ticket_channel(interaction, record, closed=True)

        self.assertTrue(changed)
        self.assertEqual(record["channel_name"], "cerrado-0155")
        channel.edit.assert_awaited_once_with(name="cerrado-0155", reason="Ticket cerrado")

    async def test_close_rename_is_idempotent_when_name_is_already_correct(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123, name="cerrado-0025", edit=AsyncMock())
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(channels=[channel]),
        )
        record = {"number": 25, "channel_name": "cerrado-0025"}

        changed = await cog.rename_ticket_channel(interaction, record, closed=True)

        self.assertFalse(changed)
        channel.edit.assert_not_awaited()

    async def test_reopen_rename_restores_original_channel_name(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123, name="cerrado-0025", edit=AsyncMock())
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(channels=[channel]),
        )
        record = {
            "number": 25,
            "channel_name": "cerrado-0025",
            "original_channel_name": "ticket-0025",
        }

        changed = await cog.rename_ticket_channel(interaction, record, closed=False)

        self.assertTrue(changed)
        self.assertEqual(record["channel_name"], "ticket-0025")
        channel.edit.assert_awaited_once_with(name="ticket-0025", reason="Ticket reabierto")

    async def test_closed_rename_avoids_duplicate_channel_names(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123456, name="ticket-0025", edit=AsyncMock())
        other_channel = SimpleNamespace(id=999, name="cerrado-0025")
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(channels=[other_channel, channel]),
        )
        record = {"number": 25, "channel_name": "ticket-0025"}

        changed = await cog.rename_ticket_channel(interaction, record, closed=True)

        self.assertTrue(changed)
        self.assertEqual(record["channel_name"], "cerrado-0025-123456")
        channel.edit.assert_awaited_once_with(name="cerrado-0025-123456", reason="Ticket cerrado")

    async def test_closed_rename_avoids_duplicate_suffix_names(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        channel = SimpleNamespace(id=123456, name="ticket-0025", edit=AsyncMock())
        interaction = SimpleNamespace(
            channel=channel,
            guild=SimpleNamespace(
                channels=[
                    SimpleNamespace(id=999, name="cerrado-0025"),
                    SimpleNamespace(id=998, name="cerrado-0025-123456"),
                    channel,
                ]
            ),
        )
        record = {"number": 25, "channel_name": "ticket-0025"}

        changed = await cog.rename_ticket_channel(interaction, record, closed=True)

        self.assertTrue(changed)
        self.assertEqual(record["channel_name"], "cerrado-0025-123456-2")
        channel.edit.assert_awaited_once_with(name="cerrado-0025-123456-2", reason="Ticket cerrado")

    def test_fine_ticket_resolver_role_can_close(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        record = {"ticket_type": "fine", "resolver_role_id": "55"}
        member = SimpleNamespace(
            roles=[SimpleNamespace(id=55)],
            guild_permissions=SimpleNamespace(administrator=False),
        )

        self.assertTrue(cog.can_close(member, None, record, guild_id=10))

    def test_fine_ticket_module_permission_can_delete(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.permission_service = Mock()
        cog.permission_service.can_manage_tickets.return_value = False
        cog.permission_service.can_manage_fines.return_value = True
        record = {"ticket_type": "fine", "resolver_role_id": "55"}
        member = SimpleNamespace(
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )

        self.assertTrue(cog.can_delete(member, None, guild_id=10, record=record))
        cog.permission_service.can_manage_tickets.assert_called_once_with(10, member)
        cog.permission_service.can_manage_fines.assert_called_once_with(10, member)

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

    def test_ticket_owner_permissions_use_configured_channel_permissions(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        panel = {
            "permissions": {
                "owner_permissions": ["view_channel", "read_message_history", "invalid"],
            }
        }

        self.assertEqual(
            cog.ticket_owner_permissions(panel),
            {"view_channel", "read_message_history"},
        )

    def test_ticket_owner_permissions_keep_legacy_default(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)

        self.assertEqual(
            cog.ticket_owner_permissions({"permissions": {}}),
            {"view_channel", "send_messages", "read_message_history", "attach_files", "embed_links"},
        )

    def test_option_open_message_overrides_panel_value(self):
        panel = {"ticket_open_title": "General"}
        option = {"ticket_open_title": "Soporte tecnico"}

        self.assertEqual(
            TicketRuntimeCog.option_or_panel_value(panel, option, "ticket_open_title"),
            "Soporte tecnico",
        )

    def test_empty_option_open_message_falls_back_to_panel_value(self):
        panel = {"ticket_open_title": "General"}
        option = {"ticket_open_title": ""}

        self.assertEqual(
            TicketRuntimeCog.option_or_panel_value(panel, option, "ticket_open_title"),
            "General",
        )

    def test_added_ticket_users_ignores_invalid_entries(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        record = {
            "added_users": [
                {"id": "55", "name": "Player"},
                {"id": ""},
                "invalid",
            ]
        }

        self.assertEqual(cog.added_ticket_users(record), [{"id": "55", "name": "Player"}])

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

    async def test_delete_fine_ticket_marks_fine_deleted_before_channel_delete(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        record = {
            "status": "closed",
            "ticket_type": "fine",
            "fine_id": "7",
            "panel_id": "__fine__",
        }
        cog.get_record = Mock(return_value=({"10": [record]}, record))
        cog.find_panel = Mock(return_value=None)
        cog.can_delete = Mock(return_value=True)
        cog.save_records = Mock()
        cog.fine_repo = Mock()
        cog.fine_repo.soft_delete.return_value = {
            "id": 7,
            "is_deleted": 1,
            "deleted_at": "2026-06-25T12:00:00Z",
        }
        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            user=SimpleNamespace(),
            response=SimpleNamespace(send_message=AsyncMock()),
            channel=SimpleNamespace(delete=AsyncMock()),
        )

        await cog.delete_ticket(interaction, 123)

        cog.fine_repo.soft_delete.assert_called_once_with(7)
        self.assertEqual(record["status"], "deleted")
        self.assertTrue(record["is_deleted"])
        self.assertEqual(record["deleted_at"], "2026-06-25T12:00:00Z")
        cog.save_records.assert_called_once()
        interaction.channel.delete.assert_awaited_once()

    async def test_deleted_ticket_cannot_be_closed(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        cog.get_record = Mock(return_value=({}, {"status": "deleted", "panel_id": "panel-1"}))
        cog.find_panel = Mock(return_value={"permissions": {}})
        cog.can_close = Mock(return_value=True)
        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            user=SimpleNamespace(),
            response=SimpleNamespace(send_message=AsyncMock()),
        )

        await cog.close_ticket_prompt(interaction, 123)

        interaction.response.send_message.assert_awaited_once_with(
            "Este ticket fue eliminado y ya no puede cerrarse.",
            ephemeral=True,
        )
        cog.can_close.assert_not_called()

    async def test_close_confirm_defers_before_scheduling_channel_rename(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        record = {"status": "open", "panel_id": "panel-1", "owner_id": "", "claimed_by_id": ""}
        events = []

        async def defer(**kwargs):
            events.append("defer")

        def schedule(*args, **kwargs):
            events.append("schedule")

        cog.get_record = Mock(return_value=({"10": [record]}, record))
        cog.find_panel = Mock(return_value={"permissions": {}})
        cog.can_close = Mock(return_value=True)
        cog.save_records = Mock()
        cog.schedule_ticket_channel_rename = Mock(side_effect=schedule)
        channel = SimpleNamespace(set_permissions=AsyncMock(), send=AsyncMock())
        interaction = SimpleNamespace(
            guild=SimpleNamespace(
                id=10,
                default_role=SimpleNamespace(),
                me=SimpleNamespace(),
                get_member=Mock(return_value=None),
                get_role=Mock(return_value=None),
            ),
            user=SimpleNamespace(),
            response=SimpleNamespace(defer=AsyncMock(side_effect=defer), send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            channel=channel,
        )

        await cog.close_ticket_confirm(interaction, 123)

        self.assertEqual(events[:2], ["defer", "schedule"])
        interaction.followup.send.assert_awaited_once_with("Ticket cerrado.", ephemeral=True)
        interaction.response.send_message.assert_not_awaited()

    async def test_reopen_defers_before_scheduling_channel_rename(self):
        cog = TicketRuntimeCog.__new__(TicketRuntimeCog)
        record = {"status": "closed", "panel_id": "panel-1", "owner_id": ""}
        events = []

        async def defer(**kwargs):
            events.append("defer")

        def schedule(*args, **kwargs):
            events.append("schedule")

        cog.get_record = Mock(return_value=({"10": [record]}, record))
        cog.find_panel = Mock(return_value={"permissions": {}})
        cog.can_reopen = Mock(return_value=True)
        cog.save_records = Mock()
        cog.schedule_ticket_channel_rename = Mock(side_effect=schedule)
        channel = SimpleNamespace(set_permissions=AsyncMock(), send=AsyncMock())
        interaction = SimpleNamespace(
            guild=SimpleNamespace(
                id=10,
                default_role=SimpleNamespace(),
                me=SimpleNamespace(),
                get_member=Mock(return_value=None),
                get_role=Mock(return_value=None),
            ),
            user=SimpleNamespace(mention="<@99>"),
            response=SimpleNamespace(defer=AsyncMock(side_effect=defer), send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            channel=channel,
        )

        await cog.reopen_ticket(interaction, 123)

        self.assertEqual(events[:2], ["defer", "schedule"])
        interaction.followup.send.assert_awaited_once_with("Ticket reabierto.", ephemeral=True)
        interaction.response.send_message.assert_not_awaited()

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
