import json
import os

from repositories.balance_repository import DATA_DIR

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


class ConfigRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(CONFIG_FILE):
            self.save({})

    def load(self):
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save(self, data):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_guild_config(self, guild_id):
        data = self.load()
        return data.get(str(guild_id), {})

    def set_channel(self, guild_id, channel_type, channel_id):
        data = self.load()
        gid = str(guild_id)
        if gid not in data:
            data[gid] = {}

        data[gid][channel_type] = str(channel_id)
        self.save(data)
