import unittest

from services.permission_service import (
    DASHBOARD_SECTION_MODULES,
    MODULE_AUDIT,
    MODULE_EXPORT_ECONOMY,
    MODULE_FINES,
    MODULE_PERMISSIONS,
    MODULE_TEMPLATES,
    PERMISSION_ECONOMY,
    PERMISSION_GLOBAL,
    PERMISSION_PERMISSIONS,
    PERMISSION_REPORTS,
    PERMISSION_TEMPLATES,
    PERMISSION_TICKETS,
    PermissionService,
)


class PermissionServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = PermissionService()

    def test_global_permission_grants_any_module(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_GLOBAL]}
        self.assertTrue(
            self.service.has_module_access("1", MODULE_AUDIT, role_ids=["10"])
        )

    def test_audit_requires_permissions_module(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_TICKETS]}
        self.assertFalse(
            self.service.has_module_access("1", MODULE_AUDIT, role_ids=["10"])
        )

        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_PERMISSIONS]}
        self.assertTrue(
            self.service.has_module_access("1", MODULE_AUDIT, role_ids=["10"])
        )

    def test_fines_keep_legacy_compatibility_for_reports_and_tickets(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_TICKETS]}
        self.assertTrue(
            self.service.has_module_access("1", MODULE_FINES, role_ids=["10"])
        )

        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_REPORTS]}
        self.assertTrue(
            self.service.has_module_access("1", MODULE_FINES, role_ids=["10"])
        )

    def test_exports_use_module_specific_permissions(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_TEMPLATES]}
        self.assertFalse(
            self.service.has_module_access("1", MODULE_EXPORT_ECONOMY, role_ids=["10"])
        )

        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_ECONOMY]}
        self.assertTrue(
            self.service.has_module_access("1", MODULE_EXPORT_ECONOMY, role_ids=["10"])
        )

    def test_dashboard_access_detects_non_admin_template_manager(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_TEMPLATES]}
        self.assertTrue(
            self.service.has_any_dashboard_access("1", role_ids=["10"])
        )
        self.assertEqual(DASHBOARD_SECTION_MODULES["templates"], MODULE_TEMPLATES)

    def test_unknown_module_is_denied_by_default(self):
        self.service.get_role_permissions = lambda guild_id: {"10": [PERMISSION_GLOBAL]}
        self.assertFalse(
            self.service.has_module_access("1", "unknown-module", role_ids=[], is_admin=False, required_permissions=())
        )


if __name__ == "__main__":
    unittest.main()
