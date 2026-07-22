import unittest

from repositories.pagination import normalize_page, normalize_page_size, page_response
from src.neox.dashboard.assets import load_dashboard_template, resolve_dashboard_static_path
from src.neox.dashboard.auth import oauth_configured
from src.neox.dashboard.bootstrap import select_dashboard_guilds
from src.neox.dashboard.security import DashboardCookieManager, safe_dashboard_next
import web_dashboard


class FakeActiveAvalonianRepository:
    def load(self):
        return {
            "456": {
                "123": {
                    "27": {
                        "guild_id": 456,
                        "caller_id": 123,
                        "numero_ava": 27,
                        "title": "Ava de prueba",
                        "caller_name": "Neox",
                        "finalized": True,
                        "cancelled": False,
                        "report_sent": False,
                    },
                    "28": {
                        "guild_id": 456,
                        "caller_id": 123,
                        "numero_ava": 28,
                        "title": "Ava enviada",
                        "finalized": True,
                        "cancelled": False,
                        "report_sent": True,
                    },
                },
                "789": {
                    "30": {
                        "guild_id": 456,
                        "caller_id": 789,
                        "numero_ava": 30,
                        "title": "Ava de otro caller",
                        "caller_name": "Otro",
                        "finalized": True,
                        "cancelled": False,
                        "report_sent": False,
                    }
                },
            }
        }


class DashboardHelperTests(unittest.TestCase):
    def test_ticket_panel_options_keep_custom_open_message(self):
        panel = web_dashboard.normalize_ticket_panel({
            "options": [
                {
                    "label": "Soporte",
                    "ticket_open_title": "Soporte tecnico",
                    "ticket_open_description": "Describe el problema.",
                    "ticket_open_color": "#38bdf8",
                }
            ]
        })

        option = panel["options"][0]
        self.assertEqual(option["ticket_open_title"], "Soporte tecnico")
        self.assertEqual(option["ticket_open_description"], "Describe el problema.")
        self.assertEqual(option["ticket_open_color"], "#38bdf8")

    def test_report_calculator_options_read_active_avalonian_repository(self):
        original_repository = web_dashboard.ActiveAvalonianRepository
        web_dashboard.ActiveAvalonianRepository = FakeActiveAvalonianRepository
        try:
            calculators = web_dashboard.get_active_report_calculators_for_user("456", "123")
            state = web_dashboard.get_active_avalonian_state("456", "123", "27")
        finally:
            web_dashboard.ActiveAvalonianRepository = original_repository

        self.assertEqual(
            calculators,
            [
                {
                    "numero_ava": "27",
                    "title": "Ava de prueba",
                    "caller_id": "123",
                    "caller_name": "Neox",
                    "report_sent": False,
                    "report_generated": False,
                    "report_rejected": False,
                }
            ],
        )
        self.assertEqual(state["title"], "Ava de prueba")

    def test_report_calculator_admin_options_include_all_callers(self):
        original_repository = web_dashboard.ActiveAvalonianRepository
        web_dashboard.ActiveAvalonianRepository = FakeActiveAvalonianRepository
        try:
            calculators = web_dashboard.get_active_report_calculators("456")
        finally:
            web_dashboard.ActiveAvalonianRepository = original_repository

        self.assertEqual(
            [(item["caller_id"], item["numero_ava"]) for item in calculators],
            [("789", "30"), ("123", "27")],
        )

    def test_report_calculator_access_allows_discord_admin(self):
        original_get_bot_guild_ids = web_dashboard.get_bot_guild_ids
        web_dashboard.get_bot_guild_ids = lambda: {"456"}
        try:
            session = {
                "user": {"id": "999"},
                "guilds": [{"id": "456", "name": "Servidor"}],
                "admin_guilds": [{"id": "456", "name": "Servidor"}],
            }
            handler = web_dashboard.DashboardHandler.__new__(web_dashboard.DashboardHandler)
            allowed = handler.can_access_report_calculator(
                session,
                "456",
                "123",
            )
        finally:
            web_dashboard.get_bot_guild_ids = original_get_bot_guild_ids

        self.assertTrue(allowed)

    def test_report_calculator_access_keeps_non_admin_limited_to_caller(self):
        original_get_bot_guild_ids = web_dashboard.get_bot_guild_ids
        web_dashboard.get_bot_guild_ids = lambda: {"456"}
        try:
            session = {
                "user": {"id": "999"},
                "guilds": [{"id": "456", "name": "Servidor"}],
                "admin_guilds": [],
            }
            handler = web_dashboard.DashboardHandler.__new__(web_dashboard.DashboardHandler)
            allowed = handler.can_access_report_calculator(
                session,
                "456",
                "123",
            )
        finally:
            web_dashboard.get_bot_guild_ids = original_get_bot_guild_ids

        self.assertFalse(allowed)

    def test_report_calculator_participants_follow_template_role_order(self):
        state = {
            "guild_id": 456,
            "caller_id": 123,
            "numero_ava": 27,
            "template": {
                "roles": [
                    "MainTank",
                    "OffTank",
                    "Healer",
                    "SC",
                    "Raiz",
                    "LooterScout",
                    "DPS",
                    "DPS",
                    "DPS",
                    "DPS",
                ]
            },
            "slots": {
                "DPS": 701,
                "DPS#2": 702,
                "DPS#3": 703,
                "DPS#4": 704,
                "Healer": 301,
                "LooterScout": 601,
                "MainTank": 101,
                "OffTank": 201,
                "Raiz": 501,
                "SC": 401,
            },
        }

        original_display_name = web_dashboard.get_discord_member_display_name
        web_dashboard.get_discord_member_display_name = lambda guild_id, user_id: f"Usuario {user_id}"
        try:
            calculator = web_dashboard.serialize_report_calculator_state(state)
        finally:
            web_dashboard.get_discord_member_display_name = original_display_name

        self.assertEqual(
            [participant["slot"] for participant in calculator["participants"]],
            [
                "MainTank",
                "OffTank",
                "Healer",
                "SC",
                "Raiz",
                "LooterScout",
                "DPS",
                "DPS",
                "DPS",
                "DPS",
            ],
        )

    def test_dashboard_user_name_resolves_missing_balance_names(self):
        original_display_name = web_dashboard.get_discord_member_display_name
        web_dashboard.get_discord_member_display_name = lambda guild_id, user_id: "Neox"
        try:
            name = web_dashboard.resolve_dashboard_user_name("456", "123", "")
        finally:
            web_dashboard.get_discord_member_display_name = original_display_name

        self.assertEqual(name, "Neox")

    def test_dashboard_user_name_falls_back_to_user_id_label(self):
        original_display_name = web_dashboard.get_discord_member_display_name
        web_dashboard.get_discord_member_display_name = lambda guild_id, user_id: ""
        try:
            name = web_dashboard.resolve_dashboard_user_name("456", "123", "Usuario 123")
        finally:
            web_dashboard.get_discord_member_display_name = original_display_name

        self.assertEqual(name, "Usuario 123")

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

    def test_session_cookie_secure_enabled_for_production_https(self):
        manager = DashboardCookieManager(
            session_cookie_name="dashboard_session",
            state_cookie_name="dashboard_state",
            session_secret="test-secret",
            cookie_secure=True,
        )

        header = manager.make_session_cookie("encoded-session", max_age=3600)

        self.assertIn("Secure", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)

    def test_session_cookie_secure_disabled_for_local_http(self):
        manager = DashboardCookieManager(
            session_cookie_name="dashboard_session",
            state_cookie_name="dashboard_state",
            session_secret="test-secret",
            cookie_secure=False,
        )

        header = manager.make_session_cookie("encoded-session", max_age=3600)

        self.assertNotIn("Secure", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)

    def test_state_cookie_keeps_security_attributes(self):
        manager = DashboardCookieManager(
            session_cookie_name="dashboard_session",
            state_cookie_name="dashboard_state",
            session_secret="test-secret",
            cookie_secure=True,
        )

        header = manager.make_state_cookie("oauth-state")

        self.assertIn("Secure", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)

    def test_oauth_configured_requires_both_values(self):
        self.assertTrue(oauth_configured("client-id", "client-secret"))
        self.assertFalse(oauth_configured("client-id", ""))
        self.assertFalse(oauth_configured("", "client-secret"))

    def test_load_dashboard_template_reads_login_template(self):
        template = load_dashboard_template("login.html")
        self.assertIn("<!doctype html>", template)
        self.assertIn("<!--DASHBOARD_NEXT_INPUT-->", template)
        self.assertIn('rel="icon"', template)

    def test_load_dashboard_template_reads_landing_template(self):
        template = load_dashboard_template("landing.html")
        self.assertIn("<!doctype html>", template)
        self.assertIn("AvalonBot", template)
        self.assertIn("/static/css/landing.css", template)
        self.assertIn("<!--BOT_INVITE_URL-->", template)
        self.assertIn('rel="icon"', template)

    def test_build_bot_invite_url_uses_dashboard_client_id(self):
        original_client_id = web_dashboard.DASHBOARD_CLIENT_ID
        web_dashboard.DASHBOARD_CLIENT_ID = "1234567890"
        try:
            invite_url = web_dashboard.build_bot_invite_url()
        finally:
            web_dashboard.DASHBOARD_CLIENT_ID = original_client_id

        self.assertIn("https://discord.com/oauth2/authorize?", invite_url)
        self.assertIn("client_id=1234567890", invite_url)
        self.assertIn("scope=bot+applications.commands", invite_url)
        self.assertIn("permissions=8", invite_url)

    def test_render_landing_html_injects_bot_invite_url(self):
        original_builder = web_dashboard.build_bot_invite_url
        web_dashboard.build_bot_invite_url = lambda: "https://discord.com/oauth2/authorize?client_id=test"
        try:
            rendered = web_dashboard.render_landing_html()
        finally:
            web_dashboard.build_bot_invite_url = original_builder

        self.assertIn("Invitar bot", rendered)
        self.assertIn("client_id=test", rendered)
        self.assertNotIn("<!--BOT_INVITE_URL-->", rendered)

    def test_resolve_dashboard_static_path_blocks_traversal(self):
        static_path = resolve_dashboard_static_path("css/login.css")
        self.assertIsNotNone(static_path)
        self.assertTrue(str(static_path).endswith("login.css"))
        self.assertIsNone(resolve_dashboard_static_path("../web_dashboard.py"))

    def test_resolve_dashboard_static_path_reads_landing_assets(self):
        css_path = resolve_dashboard_static_path("css/landing.css")
        js_path = resolve_dashboard_static_path("js/landing.js")
        self.assertIsNotNone(css_path)
        self.assertTrue(str(css_path).endswith("landing.css"))
        self.assertIsNotNone(js_path)
        self.assertTrue(str(js_path).endswith("landing.js"))

    def test_root_route_serves_public_landing(self):
        original_get_session = web_dashboard.get_session_from_request
        web_dashboard.get_session_from_request = lambda handler: None
        try:
            handler = web_dashboard.DashboardHandler.__new__(web_dashboard.DashboardHandler)
            handler.path = "/"
            captured = {}

            def fake_send_text(status, content, content_type, headers=None):
                captured["status"] = status
                captured["content"] = content
                captured["content_type"] = content_type

            handler.send_text = fake_send_text
            handler.send_redirect = lambda *args, **kwargs: captured.setdefault("redirected", True)
            handler.do_GET()
        finally:
            web_dashboard.get_session_from_request = original_get_session

        self.assertEqual(captured["status"], 200)
        self.assertEqual(captured["content_type"], "text/html")
        self.assertIn("Dashboard para Discord", captured["content"])
        self.assertIn("Invitar bot", captured["content"])
        self.assertNotIn("redirected", captured)

    def test_dashboard_redirects_to_login_with_next_when_session_missing(self):
        original_get_session = web_dashboard.get_session_from_request
        web_dashboard.get_session_from_request = lambda handler: None
        try:
            handler = web_dashboard.DashboardHandler.__new__(web_dashboard.DashboardHandler)
            handler.path = "/dashboard?tab=balances"
            captured = {}

            handler.send_text = lambda *args, **kwargs: captured.setdefault("text_called", True)
            handler.send_redirect = lambda location, headers=None: captured.update({"location": location})
            handler.do_GET()
        finally:
            web_dashboard.get_session_from_request = original_get_session

        self.assertEqual(
            captured["location"],
            "/login?remember=1&next=%2Fdashboard%3Ftab%3Dbalances",
        )

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

    def test_select_dashboard_guilds_includes_allowed_guilds_without_local_data(self):
        guilds, selected = select_dashboard_guilds(
            [{"id": "1", "name": "Guild One"}],
            requested_guild_id="2",
            allowed_guilds={"1": "Guild One", "2": "Guild Two"},
            bot_guild_ids={"1", "2"},
        )

        self.assertEqual(selected, "2")
        self.assertEqual(guilds, [
            {"id": "1", "name": "Guild One"},
            {"id": "2", "name": "Guild Two"},
        ])

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
