import unittest

from repositories.pagination import normalize_page, normalize_page_size, page_response
from src.neox.dashboard.assets import load_dashboard_template, resolve_dashboard_static_path
from src.neox.dashboard.auth import oauth_configured
from src.neox.dashboard.bootstrap import select_dashboard_guilds
from src.neox.dashboard.security import DashboardCookieManager, safe_dashboard_next


class DashboardHelperTests(unittest.TestCase):
    def test_safe_dashboard_next_only_allows_dashboard_paths(self):
        self.assertEqual(safe_dashboard_next("/dashboard"), "/dashboard")
        self.assertEqual(safe_dashboard_next("/dashboard?tab=balances"), "/dashboard?tab=balances")
        self.assertEqual(safe_dashboard_next("https://example.com"), "/dashboard")

    def test_cookie_manager_round_trip(self):
        manager = DashboardCookieManager(
            session_cookie_name="dashboard_session",
            state_cookie_name="dashboard_state",
            session_secret="test-secret",
        )

        encoded = manager.encode_session_cookie("session-123")

        self.assertEqual(manager.decode_session_cookie(encoded), "session-123")
        self.assertIsNone(manager.decode_session_cookie("session-123.invalid"))

    def test_oauth_configured_requires_both_values(self):
        self.assertTrue(oauth_configured("client-id", "client-secret"))
        self.assertFalse(oauth_configured("client-id", ""))
        self.assertFalse(oauth_configured("", "client-secret"))

    def test_load_dashboard_template_reads_login_template(self):
        template = load_dashboard_template("login.html")
        self.assertIn("<!doctype html>", template)
        self.assertIn("<!--DASHBOARD_NEXT_INPUT-->", template)

    def test_resolve_dashboard_static_path_blocks_traversal(self):
        static_path = resolve_dashboard_static_path("css/login.css")
        self.assertIsNotNone(static_path)
        self.assertTrue(str(static_path).endswith("login.css"))
        self.assertIsNone(resolve_dashboard_static_path("../web_dashboard.py"))

    def test_select_dashboard_guilds_prefers_requested_guild(self):
        guilds, selected = select_dashboard_guilds(
            [
                {"id": "1", "name": "Servidor 1"},
                {"id": "2", "name": "Guild Two"},
            ],
            requested_guild_id="2",
            allowed_guilds={"1": "Guild One", "2": "Guild Two"},
            bot_guild_ids={"1", "2"},
        )
        self.assertEqual(selected, "2")
        self.assertEqual(guilds[0]["name"], "Guild One")

    def test_select_dashboard_guilds_filters_unavailable_guilds(self):
        guilds, selected = select_dashboard_guilds(
            [{"id": "1", "name": "Guild One"}, {"id": "2", "name": "Guild Two"}],
            requested_guild_id="2",
            allowed_guilds={"1": "Guild One"},
            bot_guild_ids={"1"},
        )
        self.assertEqual(selected, "1")
        self.assertEqual(guilds, [{"id": "1", "name": "Guild One"}])

    def test_pagination_normalization_clamps_invalid_values(self):
        self.assertEqual(normalize_page("0"), 1)
        self.assertEqual(normalize_page("-4"), 1)
        self.assertEqual(normalize_page_size("0"), 1)
        self.assertEqual(normalize_page_size("1000"), 100)

    def test_page_response_includes_metadata_and_alias(self):
        payload = page_response([{"id": 1}], 2, 10, 21, item_key="records")
        self.assertEqual(payload["records"], [{"id": 1}])
        self.assertEqual(payload["items"], [{"id": 1}])
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["page_size"], 10)
        self.assertEqual(payload["total_items"], 21)
        self.assertEqual(payload["total_pages"], 3)


if __name__ == "__main__":
    unittest.main()
