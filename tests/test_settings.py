import importlib
import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch

try:
    import dotenv
except ModuleNotFoundError:
    dotenv = None


class SettingsTests(unittest.TestCase):
    def tearDown(self):
        import src.neox.config.settings as settings_module

        importlib.reload(settings_module)

    def reload_settings(self, env):
        with patch.dict(os.environ, env, clear=True):
            patcher = patch.object(dotenv, "load_dotenv", return_value=False) if dotenv else nullcontext()
            with patcher:
                import src.neox.config.settings as settings_module

                return importlib.reload(settings_module)

    def test_bot_token_falls_back_to_token_when_economy_token_is_missing(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
        })

        self.assertEqual(settings_module.ECONOMY_TOKEN, "primary-token")
        self.assertEqual(settings_module.require_bot_token(), "primary-token")

    def test_dashboard_public_url_defaults_from_redirect_uri(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_REDIRECT_URI": "http://localhost:8000/oauth/callback",
        })

        self.assertEqual(settings_module.DASHBOARD_PUBLIC_URL, "http://localhost:8000")

    def test_dashboard_cookie_secure_can_be_enabled_from_env(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_COOKIE_SECURE": "true",
        })

        self.assertTrue(settings_module.DASHBOARD_COOKIE_SECURE)
        self.assertTrue(settings_module.DASHBOARD_SETTINGS.cookie_secure)

    def test_dashboard_cookie_secure_defaults_to_local_http_compatible(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
        })

        self.assertFalse(settings_module.DASHBOARD_COOKIE_SECURE)
        self.assertFalse(settings_module.DASHBOARD_SETTINGS.cookie_secure)

    def test_dashboard_bind_defaults_to_loopback(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
        })

        self.assertEqual(settings_module.DASHBOARD_HOST, "127.0.0.1")
        self.assertEqual(settings_module.DASHBOARD_PORT, 8000)
        self.assertEqual(settings_module.DASHBOARD_SETTINGS.host, "127.0.0.1")
        self.assertEqual(settings_module.DASHBOARD_SETTINGS.port, 8000)

    def test_dashboard_bind_can_be_overridden_from_env(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_HOST": "localhost",
            "DASHBOARD_PORT": "9000",
        })

        self.assertEqual(settings_module.DASHBOARD_HOST, "localhost")
        self.assertEqual(settings_module.DASHBOARD_PORT, 9000)

    def test_dashboard_production_mode_can_be_enabled_from_env(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_ENV": "production",
        })

        self.assertEqual(settings_module.DASHBOARD_ENVIRONMENT, "production")
        self.assertTrue(settings_module.DASHBOARD_PRODUCTION_MODE)

    def test_dashboard_production_mode_can_be_enabled_from_app_env(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "APP_ENV": "production",
        })

        self.assertEqual(settings_module.APP_ENV, "production")
        self.assertEqual(settings_module.DASHBOARD_ENVIRONMENT, "production")
        self.assertTrue(settings_module.DASHBOARD_PRODUCTION_MODE)

    def test_dashboard_production_mode_is_enabled_for_https_public_url(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_PUBLIC_URL": "https://dashboard.example.com",
        })

        self.assertTrue(settings_module.DASHBOARD_PRODUCTION_MODE)

    def test_message_content_intent_is_disabled_by_default(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
        })

        self.assertFalse(settings_module.BOT_SETTINGS.enable_message_content_intent)

    def test_message_content_intent_can_be_enabled_explicitly(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "ENABLE_MESSAGE_CONTENT_INTENT": "1",
        })

        self.assertTrue(settings_module.BOT_SETTINGS.enable_message_content_intent)

    def test_music_cog_is_enabled_by_default(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
        })

        self.assertTrue(settings_module.MUSIC_ENABLED)
        self.assertIn("cogs.music", settings_module.ECONOMY_COGS)
        self.assertTrue(settings_module.BOT_SETTINGS.music_enabled)

    def test_music_cog_can_be_disabled_from_env(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "MUSIC_ENABLED": "false",
        })

        self.assertFalse(settings_module.MUSIC_ENABLED)
        self.assertNotIn("cogs.music", settings_module.ECONOMY_COGS)
        self.assertFalse(settings_module.BOT_SETTINGS.music_enabled)

    def test_ffmpeg_path_is_exposed_in_bot_settings(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "FFMPEG_PATH": "/usr/bin/ffmpeg",
        })

        self.assertEqual(settings_module.FFMPEG_PATH, "/usr/bin/ffmpeg")
        self.assertEqual(settings_module.BOT_SETTINGS.ffmpeg_path, "/usr/bin/ffmpeg")

    def test_dashboard_startup_requires_session_secret(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
        })

        with self.assertRaises(RuntimeError):
            settings_module.validate_dashboard_startup()

    def test_dashboard_startup_requires_oauth_pair(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "DASHBOARD_SESSION_SECRET": "secret",
            "DASHBOARD_CLIENT_ID": "client-id",
        })

        with self.assertRaises(RuntimeError):
            settings_module.validate_dashboard_startup()

    def test_dashboard_startup_requires_admin_secrets_in_production(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "APP_ENV": "production",
            "DASHBOARD_SESSION_SECRET": "session-secret",
        })

        with self.assertRaises(RuntimeError) as raised:
            settings_module.validate_dashboard_startup()

        message = str(raised.exception)
        self.assertIn("DASHBOARD_ADMIN_PASSWORD_HASH", message)
        self.assertIn("DASHBOARD_ADMIN_PASSWORD_PEPPER", message)
        self.assertIn("DASHBOARD_ADMIN_DEVELOPER_IDS", message)
        self.assertNotIn("session-secret", message)

    def test_dashboard_startup_accepts_required_production_secrets(self):
        settings_module = self.reload_settings({
            "TOKEN": "primary-token",
            "APP_ENV": "production",
            "DASHBOARD_SESSION_SECRET": "session-secret",
            "DASHBOARD_ADMIN_PASSWORD_HASH": "$argon2id$v=19$m=65536,t=3,p=4$hash",
            "DASHBOARD_ADMIN_PASSWORD_PEPPER": "pepper-secret",
            "DASHBOARD_ADMIN_DEVELOPER_IDS": "123,456",
        })

        self.assertIs(settings_module.validate_dashboard_startup(), settings_module.DASHBOARD_SETTINGS)

    def test_dashboard_startup_rejects_production_placeholders(self):
        settings_module = self.reload_settings({
            "TOKEN": "your_discord_bot_token",
            "APP_ENV": "production",
            "DASHBOARD_SESSION_SECRET": "replace_with_a_long_random_secret",
            "DASHBOARD_ADMIN_PASSWORD_HASH": "$argon2id$v=19$m=65536,t=3,p=4$hash",
            "DASHBOARD_ADMIN_PASSWORD_PEPPER": "pepper-secret",
            "DASHBOARD_ADMIN_DEVELOPER_IDS": "123",
        })

        with self.assertRaises(RuntimeError) as raised:
            settings_module.validate_dashboard_startup()

        message = str(raised.exception)
        self.assertIn("TOKEN o ECONOMY_TOKEN", message)
        self.assertIn("DASHBOARD_SESSION_SECRET", message)


if __name__ == "__main__":
    unittest.main()
