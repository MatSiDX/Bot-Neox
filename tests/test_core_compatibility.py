import unittest

from repositories.config_repository import ConfigRepository
from repositories.dashboard_action_request_repository import DashboardActionRequestRepository
from repositories.permission_repository import PermissionRepository
from repositories.ping_template_repository import PingTemplateRepository
from services.config_service import ConfigService
from services.dashboard_action_service import DashboardActionService
from services.discord_metadata_service import DiscordMetadataService
from services.ping_template_service import PingTemplateService
from src.neox.core.repositories.config_repository import ConfigRepository as CoreConfigRepository
from src.neox.core.repositories.dashboard_action_request_repository import DashboardActionRequestRepository as CoreDashboardActionRequestRepository
from src.neox.core.repositories.permission_repository import PermissionRepository as CorePermissionRepository
from src.neox.core.repositories.ping_template_repository import PingTemplateRepository as CorePingTemplateRepository
from src.neox.core.services.config_service import ConfigService as CoreConfigService
from src.neox.core.services.dashboard_action_service import DashboardActionService as CoreDashboardActionService
from src.neox.core.services.discord_metadata_service import DiscordMetadataService as CoreDiscordMetadataService
from src.neox.core.services.ping_template_service import PingTemplateService as CorePingTemplateService


class CoreCompatibilityTests(unittest.TestCase):
    def test_legacy_config_service_wrapper_points_to_core(self):
        self.assertIs(ConfigService, CoreConfigService)
        self.assertIs(ConfigRepository, CoreConfigRepository)

    def test_legacy_ping_template_wrapper_points_to_core(self):
        self.assertIs(PingTemplateService, CorePingTemplateService)
        self.assertIs(PingTemplateRepository, CorePingTemplateRepository)

    def test_legacy_discord_metadata_wrapper_points_to_core(self):
        self.assertIs(DiscordMetadataService, CoreDiscordMetadataService)

    def test_legacy_dashboard_action_wrapper_points_to_core(self):
        self.assertIs(DashboardActionService, CoreDashboardActionService)
        self.assertIs(DashboardActionRequestRepository, CoreDashboardActionRequestRepository)

    def test_legacy_permission_repository_wrapper_points_to_core(self):
        self.assertIs(PermissionRepository, CorePermissionRepository)


if __name__ == "__main__":
    unittest.main()
