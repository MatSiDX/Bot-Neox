import unittest

from src.neox.core.services.discord_metadata_service import (
    DiscordMetadataCacheSettings,
    DiscordMetadataService,
)


class DiscordMetadataServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.channel_calls = 0
        self.role_calls = 0
        self.emoji_calls = 0
        self.channels_payload = [
            {"id": "10", "name": "general", "type": 0},
            {"id": "20", "name": "support", "type": 5},
            {"id": "30", "name": "tickets", "type": 4},
        ]
        self.roles_payload = [
            {"id": "1", "name": "@everyone"},
            {"id": "2", "name": "Admin"},
        ]
        self.emojis_payload = [
            {"id": "7", "name": "avalon", "animated": False},
        ]
        self.settings = DiscordMetadataCacheSettings(
            roles_ttl_seconds=10,
            channels_ttl_seconds=5,
            categories_ttl_seconds=5,
            emojis_ttl_seconds=15,
            stale_fallback_seconds=20,
        )

    def build_service(self):
        def fetch_channels(_guild_id):
            self.channel_calls += 1
            if isinstance(self.channels_payload, Exception):
                raise self.channels_payload
            return list(self.channels_payload)

        def fetch_roles(_guild_id):
            self.role_calls += 1
            if isinstance(self.roles_payload, Exception):
                raise self.roles_payload
            return list(self.roles_payload)

        def fetch_emojis(_guild_id):
            self.emoji_calls += 1
            if isinstance(self.emojis_payload, Exception):
                raise self.emojis_payload
            return list(self.emojis_payload)

        return DiscordMetadataService(
            fetch_channels=fetch_channels,
            fetch_roles=fetch_roles,
            fetch_emojis=fetch_emojis,
            cache_settings=self.settings,
            now_func=lambda: self.now,
        )

    def test_channel_bundle_uses_single_fetch_for_channels_and_categories(self):
        service = self.build_service()

        channels = service.get_channels("123")
        categories = service.get_categories("123")

        self.assertEqual(self.channel_calls, 1)
        self.assertEqual(channels, [
            {"id": "10", "name": "general"},
            {"id": "20", "name": "support"},
        ])
        self.assertEqual(categories, [
            {"id": "30", "name": "tickets"},
        ])

    def test_roles_are_returned_from_cache_until_ttl_expires(self):
        service = self.build_service()

        first = service.get_roles("123")
        second = service.get_roles("123")
        self.now += 11
        third = service.get_roles("123")

        self.assertEqual(first, [{"id": "2", "name": "Admin"}])
        self.assertEqual(second, first)
        self.assertEqual(third, first)
        self.assertEqual(self.role_calls, 2)

    def test_stale_channel_cache_is_reused_when_refresh_fails(self):
        service = self.build_service()

        initial = service.get_guild_metadata("123", kinds=["channels", "categories"])
        self.assertEqual(self.channel_calls, 1)

        self.now += 6
        self.channels_payload = RuntimeError("rate limited")
        fallback = service.get_guild_metadata("123", kinds=["channels", "categories"])

        self.assertEqual(self.channel_calls, 2)
        self.assertEqual(fallback, initial)

    def test_force_refresh_invalidates_fresh_role_entry(self):
        service = self.build_service()

        service.get_roles("123")
        service.get_roles("123", force_refresh=True)

        self.assertEqual(self.role_calls, 2)

    def test_invalidate_can_clear_specific_kind(self):
        service = self.build_service()

        service.get_roles("123")
        service.invalidate("123", kinds=["roles"])
        service.get_roles("123")

        self.assertEqual(self.role_calls, 2)


if __name__ == "__main__":
    unittest.main()
