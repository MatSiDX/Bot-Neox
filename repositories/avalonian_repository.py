import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json

AVALONIAN_FILE = os.path.join(DATA_DIR, "avalonian_interactions.json")


class AvalonianRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(AVALONIAN_FILE):
            self.save({})

    def load(self):
        return read_json(AVALONIAN_FILE, {})

    def save(self, data):
        write_json(AVALONIAN_FILE, data)

    def append(self, guild_id, interaction):
        gid = str(guild_id)

        def mutate(data):
            if gid not in data:
                data[gid] = []

            data[gid].append(interaction)
            return data

        mutate_json(AVALONIAN_FILE, {}, mutate)

    def get_by_guild(self, guild_id):
        data = self.load()
        return data.get(str(guild_id), [])
