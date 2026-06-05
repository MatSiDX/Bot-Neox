import json
import os

from repositories.balance_repository import DATA_DIR

ACTIVE_AVALONIAN_FILE = os.path.join(DATA_DIR, "active_avalonian_pings.json")


class ActiveAvalonianRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(ACTIVE_AVALONIAN_FILE):
            self.save({})

    def load(self):
        with open(ACTIVE_AVALONIAN_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save(self, data):
        with open(ACTIVE_AVALONIAN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def upsert(self, state):
        data = self.load()
        guild_id = str(state["guild_id"])
        caller_id = str(state["caller_id"])
        numero_ava = str(state["numero_ava"])

        if guild_id not in data:
            data[guild_id] = {}
        if caller_id not in data[guild_id]:
            data[guild_id][caller_id] = {}

        data[guild_id][caller_id][numero_ava] = state
        self.save(data)

    def remove(self, guild_id, caller_id, numero_ava):
        data = self.load()
        gid = str(guild_id)
        cid = str(caller_id)
        ava = str(numero_ava)

        if gid not in data or cid not in data[gid] or ava not in data[gid][cid]:
            return False

        data[gid][cid].pop(ava, None)
        if not data[gid][cid]:
            data[gid].pop(cid, None)
        if not data[gid]:
            data.pop(gid, None)

        self.save(data)
        return True

    def get_all_states(self):
        data = self.load()
        states = []
        for guild_states in data.values():
            for caller_states in guild_states.values():
                states.extend(caller_states.values())
        return states
