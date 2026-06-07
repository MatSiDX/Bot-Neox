import unittest

from services.albion_api_service import AlbionApiService
from services.albion_registration_service import (
    LEAVE_ACTION_KICK,
    AlbionRegistrationService,
)


class FakeAlbionApi(AlbionApiService):
    def __init__(self, payload):
        self.payload = payload

    async def search(self, query):
        return self.payload


class FakeRegistrationRepository:
    def __init__(self, config=None, claimed=None):
        self.config = config
        self.claimed = claimed

    def get_config(self, guild_id):
        return self.config

    def get_registration_by_player(self, guild_id, player_id):
        return self.claimed


class AlbionApiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_search_requires_exact_name(self):
        api = FakeAlbionApi(
            {
                "players": [
                    {"Id": "1", "Name": "NeoxAlt"},
                    {"Id": "2", "Name": "NeOx"},
                ]
            }
        )

        player = await api.find_player_exact("neox")

        self.assertEqual(player["Id"], "2")

    async def test_guild_search_requires_exact_name(self):
        api = FakeAlbionApi(
            {
                "guilds": [
                    {"Id": "1", "Name": "Avalon Academy"},
                    {"Id": "2", "Name": "Avalon"},
                ]
            }
        )

        guild = await api.find_guild_exact("AVALON")

        self.assertEqual(guild["Id"], "2")


class AlbionRegistrationServiceTests(unittest.TestCase):
    def config(self):
        return {
            "enabled": 1,
            "albion_guild_id": "guild-1",
            "albion_guild_name": "Mi Gremio",
            "role_id": "123",
            "leave_action": LEAVE_ACTION_KICK,
            "sync_nickname": 1,
        }

    def test_rejects_player_outside_configured_guild(self):
        service = AlbionRegistrationService(
            FakeRegistrationRepository(config=self.config())
        )
        player = {
            "Id": "player-1",
            "Name": "Neox",
            "GuildId": "other-guild",
            "GuildName": "Otro Gremio",
        }

        valid, error = service.validate_player_for_registration(10, 20, player)

        self.assertFalse(valid)
        self.assertIn("Otro Gremio", error)

    def test_rejects_character_claimed_by_another_discord_user(self):
        service = AlbionRegistrationService(
            FakeRegistrationRepository(
                config=self.config(),
                claimed={"discord_user_id": "99"},
            )
        )
        player = {
            "Id": "player-1",
            "Name": "Neox",
            "GuildId": "guild-1",
            "GuildName": "Mi Gremio",
        }

        valid, error = service.validate_player_for_registration(10, 20, player)

        self.assertFalse(valid)
        self.assertIn("otra cuenta", error)

    def test_accepts_member_of_configured_guild(self):
        service = AlbionRegistrationService(
            FakeRegistrationRepository(config=self.config())
        )
        player = {
            "Id": "player-1",
            "Name": "Neox",
            "GuildId": "guild-1",
            "GuildName": "Mi Gremio",
        }

        valid, error = service.validate_player_for_registration(10, 20, player)

        self.assertTrue(valid)
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
