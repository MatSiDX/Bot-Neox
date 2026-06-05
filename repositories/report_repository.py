import json
import os

from repositories.balance_repository import DATA_DIR

REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")


class ReportRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(REPORTS_FILE):
            self.save({})

    def load(self):
        with open(REPORTS_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save(self, data):
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def append(self, guild_id, report):
        data = self.load()
        gid = str(guild_id)
        if gid not in data:
            data[gid] = []

        data[gid].append(report)
        self.save(data)

    def get_by_guild(self, guild_id):
        data = self.load()
        return data.get(str(guild_id), [])
