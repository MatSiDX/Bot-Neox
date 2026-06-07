import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json

ACTIVE_AVALONIAN_FILE = os.path.join(DATA_DIR, "active_avalonian_pings.json")


class ActiveAvalonianRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(ACTIVE_AVALONIAN_FILE):
            self.save({})

    def load(self):
        return read_json(ACTIVE_AVALONIAN_FILE, {})

    def save(self, data):
        write_json(ACTIVE_AVALONIAN_FILE, data)

    def upsert(self, state):
        guild_id = str(state["guild_id"])
        caller_id = str(state["caller_id"])
        numero_ava = str(state["numero_ava"])

        def mutate(data):
            if guild_id not in data:
                data[guild_id] = {}
            if caller_id not in data[guild_id]:
                data[guild_id][caller_id] = {}

            data[guild_id][caller_id][numero_ava] = state
            return data

        mutate_json(ACTIVE_AVALONIAN_FILE, {}, mutate)

    def remove(self, guild_id, caller_id, numero_ava):
        gid = str(guild_id)
        cid = str(caller_id)
        ava = str(numero_ava)
        changed = {"value": False}

        def mutate(data):
            if gid not in data or cid not in data[gid] or ava not in data[gid][cid]:
                return data

            data[gid][cid].pop(ava, None)
            if not data[gid][cid]:
                data[gid].pop(cid, None)
            if not data[gid]:
                data.pop(gid, None)

            changed["value"] = True
            return data

        mutate_json(ACTIVE_AVALONIAN_FILE, {}, mutate)
        return changed["value"]

    def get_all_states(self):
        data = self.load()
        states = []
        for guild_states in data.values():
            for caller_states in guild_states.values():
                states.extend(caller_states.values())
        return states
