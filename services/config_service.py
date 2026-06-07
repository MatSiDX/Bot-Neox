from repositories.config_repository import ConfigRepository

CONFIG_REPORT_REVIEW_CHANNEL = "report_review_channel"
CONFIG_REPORT_APPROVED_CHANNEL = "report_approved_channel"
CONFIG_FINE_CHANNEL = "fine_channel"
CONFIG_FINE_ROLE = "fine_role"
CONFIG_FINE_RESOLVER_ROLE = "fine_resolver_role"
CONFIG_FINE_TICKET_CATEGORY = "fine_ticket_category"


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
