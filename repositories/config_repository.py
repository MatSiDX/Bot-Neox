import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


class ConfigRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(CONFIG_FILE):
            self.save({})

    def load(self):
        return read_json(CONFIG_FILE, {})

    def save(self, data):
        write_json(CONFIG_FILE, data)

    def get_guild_config(self, guild_id):
        data = self.load()
        return data.get(str(guild_id), {})

    def set_value(self, guild_id, key, value):
        gid = str(guild_id)

        def mutate(data):
            if gid not in data:
                data[gid] = {}

            if value in (None, ""):
                data[gid].pop(str(key), None)
            else:
                data[gid][str(key)] = str(value)
            return data

        mutate_json(CONFIG_FILE, {}, mutate)

    def set_channel(self, guild_id, channel_type, channel_id):
        self.set_value(guild_id, channel_type, channel_id)
