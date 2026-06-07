import json
import os

from repositories.balance_repository import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json

PERMISSIONS_FILE = os.path.join(DATA_DIR, "permissions.json")


class PermissionRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(PERMISSIONS_FILE):
            self.save({})

    def load(self):
        return read_json(PERMISSIONS_FILE, {})

    def save(self, data):
        write_json(PERMISSIONS_FILE, data)

    def normalize_guild_permissions(self, guild_permissions):
        if isinstance(guild_permissions, list):
            return {str(role_id): ["global"] for role_id in guild_permissions}

        if isinstance(guild_permissions, dict):
            normalized = {}
            for role_id, permissions in guild_permissions.items():
                if isinstance(permissions, list):
                    normalized[str(role_id)] = permissions
                elif isinstance(permissions, str):
                    normalized[str(role_id)] = [permissions]
                else:
                    normalized[str(role_id)] = []
            return normalized

        return {}

    def get_permissions(self, guild_id):
        data = self.load()
        return self.normalize_guild_permissions(data.get(str(guild_id), {}))

    def add_permission(self, guild_id, role_id, permission):
        gid = str(guild_id)
        role_value = str(role_id)
        permission_value = str(permission)
        changed = {"value": False}

        def mutate(data):
            data[gid] = self.normalize_guild_permissions(data.get(gid, {}))
            role_permissions = data[gid].setdefault(role_value, [])
            if permission_value in role_permissions:
                return data

            role_permissions.append(permission_value)
            changed["value"] = True
            return data

        mutate_json(PERMISSIONS_FILE, {}, mutate)
        return changed["value"]

    def remove_permission(self, guild_id, role_id, permission):
        gid = str(guild_id)
        role_value = str(role_id)
        permission_value = str(permission)
        changed = {"value": False}

        def mutate(data):
            if gid not in data:
                return data

            data[gid] = self.normalize_guild_permissions(data.get(gid, {}))
            role_permissions = data[gid].get(role_value, [])

            if permission_value == "global":
                if role_value not in data[gid]:
                    return data

                data[gid].pop(role_value, None)
                changed["value"] = True
                return data

            if permission_value not in role_permissions:
                return data

            role_permissions.remove(permission_value)
            if role_permissions:
                data[gid][role_value] = role_permissions
            else:
                data[gid].pop(role_value, None)

            changed["value"] = True
            return data

        mutate_json(PERMISSIONS_FILE, {}, mutate)
        return changed["value"]

    def set_guild_permissions(self, guild_id, permissions):
        gid = str(guild_id)
        normalized_permissions = self.normalize_guild_permissions(permissions)

        def mutate(data):
            if normalized_permissions:
                data[gid] = normalized_permissions
            else:
                data.pop(gid, None)
            return data

        mutate_json(PERMISSIONS_FILE, {}, mutate)
