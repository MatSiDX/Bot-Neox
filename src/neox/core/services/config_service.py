from src.neox.core.domain.config_keys import (
    CONFIG_FINE_CHANNEL,
    CONFIG_FINE_RESOLVER_ROLE,
    CONFIG_FINE_ROLE,
    CONFIG_FINE_TICKET_CATEGORY,
    CONFIG_REPORT_APPROVED_CHANNEL,
    CONFIG_REPORT_REVIEW_CHANNEL,
)
from src.neox.core.repositories.config_repository import ConfigRepository


class ConfigService:
    def __init__(self):
        self.repo = ConfigRepository()

    def set_channel(self, guild_id, channel_type, channel_id):
        self.repo.set_channel(guild_id, channel_type, channel_id)

    def get_channel_id(self, guild_id, channel_type):
        value = self.repo.get_guild_config(guild_id).get(channel_type)
        return int(value) if value else 0

    def set_role(self, guild_id, key, role_id):
        self.repo.set_value(guild_id, key, role_id)

    def get_role_id(self, guild_id, key):
        value = self.repo.get_guild_config(guild_id).get(key)
        return int(value) if value else 0

    def get_fine_config(self, guild_id):
        return {
            "channel_id": self.get_channel_id(guild_id, CONFIG_FINE_CHANNEL),
            "blocked_role_id": self.get_role_id(guild_id, CONFIG_FINE_ROLE),
            "resolver_role_id": self.get_role_id(guild_id, CONFIG_FINE_RESOLVER_ROLE),
            "ticket_category_id": self.get_channel_id(guild_id, CONFIG_FINE_TICKET_CATEGORY),
        }
