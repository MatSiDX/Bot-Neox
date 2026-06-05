import json
import os

from repositories.balance_repository import DATA_DIR

PERMISSIONS_FILE = os.path.join(DATA_DIR, "permissions.json")


class PermissionRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(PERMISSIONS_FILE):
            self.save({})

    def load(self):
        with open(PERMISSIONS_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save(self, data):
        with open(PERMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

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
        data = self.load()
        gid = str(guild_id)
        role_value = str(role_id)
        permission_value = str(permission)

        data[gid] = self.normalize_guild_permissions(data.get(gid, {}))
        role_permissions = data[gid].setdefault(role_value, [])

        if permission_value not in role_permissions:
            role_permissions.append(permission_value)
            self.save(data)
            return True

        return False

    def remove_permission(self, guild_id, role_id, permission):
        data = self.load()
        gid = str(guild_id)
        role_value = str(role_id)
        permission_value = str(permission)

        if gid not in data:
            return False

        data[gid] = self.normalize_guild_permissions(data.get(gid, {}))
        role_permissions = data[gid].get(role_value, [])

        if permission_value == "global":
            if role_value not in data[gid]:
                return False

            data[gid].pop(role_value, None)
            self.save(data)
            return True

        if permission_value not in role_permissions:
            return False

        role_permissions.remove(permission_value)
        if role_permissions:
            data[gid][role_value] = role_permissions
        else:
            data[gid].pop(role_value, None)

        self.save(data)
        return True
