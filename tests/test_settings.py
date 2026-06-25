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


if __name__ == "__main__":
    unittest.main()
