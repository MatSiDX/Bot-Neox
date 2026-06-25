import os
import tempfile
import unittest
from unittest.mock import patch

from src.neox.core.repositories.config_repository import ConfigRepository
from src.neox.core.repositories.permission_repository import PermissionRepository


class JsonToSqliteMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = os.path.join(self.temp_dir.name, "bot.sqlite3")
        self.config_file = os.path.join(self.temp_dir.name, "config.json")
        self.permissions_file = os.path.join(self.temp_dir.name, "permissions.json")
        os.makedirs(self.temp_dir.name, exist_ok=True)
        patches = [
            patch("repositories.database.DATA_DIR", self.temp_dir.name),
            patch("repositories.database.DATABASE_FILE", self.database_file),
            patch("src.neox.core.repositories.config_repository.DATA_DIR", self.temp_dir.name),
            patch("src.neox.core.repositories.config_repository.CONFIG_FILE", self.config_file),
            patch("src.neox.core.repositories.permission_repository.DATA_DIR", self.temp_dir.name),
            patch("src.neox.core.repositories.permission_repository.PERMISSIONS_FILE", self.permissions_file),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.addCleanup(self.temp_dir.cleanup)

    def test_config_repository_migrates_json_once_and_keeps_dual_write(self):
        with open(self.config_file, "w", encoding="utf-8") as handle:
            handle.write('{"10":{"report_review_channel":"123","report_approved_channel":"456"}}')

        repo = ConfigRepository()

        self.assertEqual(
            repo.get_guild_config("10"),
            {
                "report_review_channel": "123",
                "report_approved_channel": "456",
            },
        )

        repo.set_value("10", "report_review_channel", "789")

        self.assertEqual(repo.get_guild_config("10")["report_review_channel"], "789")
        with open(self.config_file, "r", encoding="utf-8") as handle:
            self.assertIn('"report_review_channel": "789"', handle.read())

        repo_again = ConfigRepository()
        self.assertEqual(repo_again.get_guild_config("10")["report_review_channel"], "789")

    def test_permission_repository_migrates_json_and_preserves_legacy_file(self):
        with open(self.permissions_file, "w", encoding="utf-8") as handle:
            handle.write('{"10":{"111":["tickets","permisos"],"222":"global"}}')

        repo = PermissionRepository()

        permissions = repo.get_permissions("10")
        self.assertEqual(permissions["222"], ["global"])
        self.assertCountEqual(permissions["111"], ["tickets", "permisos"])

        changed = repo.add_permission("10", "111", "informes")
        self.assertTrue(changed)
        self.assertIn("informes", repo.get_permissions("10")["111"])

        with open(self.permissions_file, "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn('"informes"', content)
        self.assertIn('"222"', content)

    def test_permission_set_guild_permissions_is_idempotent(self):
        repo = PermissionRepository()

        repo.set_guild_permissions("10", {"111": ["tickets", "tickets", "permisos"]})
        first = repo.get_permissions("10")
        repo.set_guild_permissions("10", first)
        second = repo.get_permissions("10")

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
