import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from services.permission_service import MODULE_ADMIN_PANEL, PERMISSION_PERMISSIONS, PERMISSION_PING, PermissionService


class PermissionServiceTests(unittest.TestCase):
    def test_discord_administrator_permission_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = SimpleNamespace(
            guild_permissions=SimpleNamespace(administrator=True),
            roles=[],
        )

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_administrator_role_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = SimpleNamespace(
            id=20,
            guild_permissions=SimpleNamespace(administrator=False),
            guild=SimpleNamespace(owner_id=99),
            roles=[
                SimpleNamespace(
                    id=55,
                    permissions=SimpleNamespace(administrator=True),
                )
            ],
        )

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_guild_owner_grants_bot_permission(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()
        member = SimpleNamespace(
            id=20,
            guild_permissions=SimpleNamespace(administrator=False),
            guild=SimpleNamespace(owner_id=20),
            roles=[],
        )

        self.assertTrue(service.has_permission(10, member, PERMISSION_PING))
        service.repo.get_permissions.assert_not_called()

    def test_admin_panel_uses_sensitive_permissions(self):
        service = PermissionService.__new__(PermissionService)
        service.repo = Mock()

        self.assertEqual(service.get_required_permissions(MODULE_ADMIN_PANEL), (PERMISSION_PERMISSIONS,))


if __name__ == "__main__":
    unittest.main()
