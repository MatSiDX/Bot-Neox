import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from services.permission_service import (
    MODULE_ADMIN_PANEL,
    PERMISSION_ADMIN_PANEL_SYSTEM,
    PERMISSION_MANAGE_TEMPLATES,
    PERMISSION_PING,
    PERMISSION_PING_USE,
    PERMISSION_ROLES_EDIT,
    PERMISSION_TEMPLATES_CREATE,
    PermissionService,
)


def make_member(*, member_id=20, role_ids=None, administrator=False, owner_id=99):
    role_ids = role_ids or []
    return SimpleNamespace(
        id=member_id,
        guild_permissions=SimpleNamespace(administrator=administrator),
        guild=SimpleNamespace(owner_id=owner_id),
        roles=[
            SimpleNamespace(
                id=role_id,
                permissions=SimpleNamespace(administrator=False),
            )
            for role_id in role_ids
        ],
    )


class PermissionServiceTests(unittest.TestCase):
    def test_discord_administrator_permission_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = make_member(administrator=True)

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_administrator_role_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = make_member(role_ids=[55])
        member.roles[0].permissions.administrator = True

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_guild_owner_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = make_member(member_id=20, owner_id=20)

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_admin_panel_uses_system_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()

        self.assertEqual(
            service.get_required_permissions(MODULE_ADMIN_PANEL),
            (PERMISSION_ADMIN_PANEL_SYSTEM, "global"),
        )

    def test_legacy_permissions_expand_to_granular_permissions(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        service.repo.get_permissions.return_value = {
            "111": ["tickets", "permisos"],
        }

        permissions = service.get_role_permissions("10")

        self.assertIn(PERMISSION_ROLES_EDIT, permissions["111"])
        self.assertIn(PERMISSION_MANAGE_TEMPLATES, permissions["111"])
        self.assertIn(PERMISSION_ADMIN_PANEL_SYSTEM, permissions["111"])
        self.assertIn("tickets.records.close", permissions["111"])
        service.repo.set_guild_permissions.assert_called_once()

    def test_validate_role_permission_update_blocks_self_role_edit_without_admin(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        service.repo.get_permissions.return_value = {
            "10": [PERMISSION_ROLES_EDIT, PERMISSION_MANAGE_TEMPLATES],
        }
        member = make_member(role_ids=[10])

        error = service.validate_role_permission_update(
            "55",
            member,
            "10",
            [PERMISSION_TEMPLATES_CREATE],
        )

        self.assertEqual(error, "No puedes editar permisos de un rol que ya posees.")

    def test_validate_role_permission_update_allows_self_role_edit_for_administrator(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        service.repo.get_permissions.return_value = {}
        member = make_member(role_ids=[10], administrator=True)

        error = service.validate_role_permission_update(
            "55",
            member,
            "10",
            [PERMISSION_TEMPLATES_CREATE],
        )

        self.assertIsNone(error)

    def test_has_permission_accepts_legacy_key_alias(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        service.repo.get_permissions.return_value = {
            "10": [PERMISSION_PING_USE],
        }
        member = make_member(role_ids=[10])

        self.assertTrue(service.has_permission("55", member, PERMISSION_PING))


if __name__ == "__main__":
    unittest.main()
