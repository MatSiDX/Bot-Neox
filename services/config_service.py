from repositories.config_repository import ConfigRepository

CONFIG_REPORT_REVIEW_CHANNEL = "report_review_channel"
CONFIG_REPORT_APPROVED_CHANNEL = "report_approved_channel"


class ConfigService:
    def __init__(self):
        self.repo = ConfigRepository()

    def set_channel(self, guild_id, channel_type, channel_id):
        self.repo.set_channel(guild_id, channel_type, channel_id)

    def get_channel_id(self, guild_id, channel_type):
        value = self.repo.get_guild_config(guild_id).get(channel_type)
        return int(value) if value else 0
