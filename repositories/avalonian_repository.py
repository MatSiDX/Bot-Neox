import json
import os

from repositories.balance_repository import DATA_DIR

AVALONIAN_FILE = os.path.join(DATA_DIR, "avalonian_interactions.json")


class AvalonianRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(AVALONIAN_FILE):
            self.save({})

    def load(self):
        with open(AVALONIAN_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save(self, data):
        with open(AVALONIAN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def append(self, guild_id, interaction):
        data = self.load()
        gid = str(guild_id)

        if gid not in data:
            data[gid] = []

        data[gid].append(interaction)
        self.save(data)

    def get_by_guild(self, guild_id):
        data = self.load()
        return data.get(str(guild_id), [])
