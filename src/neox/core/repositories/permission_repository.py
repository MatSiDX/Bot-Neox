import os

from repositories.database import get_connection, init_database, utc_now_iso
from src.neox.config.settings import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json


PERMISSIONS_FILE = os.path.join(DATA_DIR, "permissions.json")


class PermissionRepository:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(PERMISSIONS_FILE):
            write_json(PERMISSIONS_FILE, {})
        init_database()
        self._migrate_json_if_needed()

    def load(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT guild_id, role_id, permission
                FROM role_permissions
                ORDER BY guild_id, role_id, permission
                """
            ).fetchall()

        if rows:
            data = {}
            for row in rows:
                data.setdefault(str(row["guild_id"]), {}).setdefault(str(row["role_id"]), []).append(str(row["permission"]))
            return data

        return self._load_legacy_json()

    def save(self, data):
        normalized = self._normalize_storage(data)
        write_json(PERMISSIONS_FILE, normalized)
        self._replace_all_sqlite(normalized)

    def normalize_guild_permissions(self, guild_permissions):
        if isinstance(guild_permissions, list):
            return {str(role_id): ["global"] for role_id in guild_permissions}

        if isinstance(guild_permissions, dict):
            normalized = {}
            for role_id, permissions in guild_permissions.items():
                if isinstance(permissions, list):
                    values = [str(permission) for permission in permissions if str(permission).strip()]
                elif isinstance(permissions, str):
                    values = [permissions] if permissions.strip() else []
                else:
                    values = []
                values = list(dict.fromkeys(values))
                if values:
                    normalized[str(role_id)] = values
            return normalized

        return {}

    def get_permissions(self, guild_id):
        guild_id = str(guild_id)
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT role_id, permission
                FROM role_permissions
                WHERE guild_id = ?
                ORDER BY role_id, permission
                """,
                (guild_id,),
            ).fetchall()

        if rows:
            permissions = {}
            for row in rows:
                permissions.setdefault(str(row["role_id"]), []).append(str(row["permission"]))
            return permissions

        legacy = self._load_legacy_json().get(guild_id, {})
        normalized_legacy = self.normalize_guild_permissions(legacy)
        if normalized_legacy:
            self._replace_guild_permissions_sqlite(guild_id, normalized_legacy)
            return normalized_legacy
        return {}

    def add_permission(self, guild_id, role_id, permission):
        guild_id = str(guild_id)
        role_id = str(role_id)
        permission = str(permission)
        current = self.get_permissions(guild_id)
        role_permissions = current.setdefault(role_id, [])
        if permission in role_permissions:
            return False

        role_permissions.append(permission)
        self.set_guild_permissions(guild_id, current)
        return True

    def remove_permission(self, guild_id, role_id, permission):
        guild_id = str(guild_id)
        role_id = str(role_id)
        permission = str(permission)
        current = self.get_permissions(guild_id)
        if role_id not in current:
            return False

        if permission == "global":
            current.pop(role_id, None)
            self.set_guild_permissions(guild_id, current)
            return True

        role_permissions = list(current.get(role_id, []))
        if permission not in role_permissions:
            return False

        role_permissions.remove(permission)
        if role_permissions:
            current[role_id] = role_permissions
        else:
            current.pop(role_id, None)
        self.set_guild_permissions(guild_id, current)
        return True

    def set_guild_permissions(self, guild_id, permissions):
        guild_id = str(guild_id)
        normalized = self.normalize_guild_permissions(permissions)
        self._replace_guild_permissions_sqlite(guild_id, normalized)

        def mutate(data):
            data = self._normalize_storage(data)
            if normalized:
                data[guild_id] = normalized
            else:
                data.pop(guild_id, None)
            return data

        mutate_json(PERMISSIONS_FILE, {}, mutate)

    def _load_legacy_json(self):
        data = read_json(PERMISSIONS_FILE, {})
        return self._normalize_storage(data)

    def _normalize_storage(self, data):
        if not isinstance(data, dict):
            return {}

        normalized = {}
        for guild_id, guild_permissions in data.items():
            clean = self.normalize_guild_permissions(guild_permissions)
            if clean:
                normalized[str(guild_id)] = clean
        return normalized

    def _migrate_json_if_needed(self):
        with get_connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM role_permissions").fetchone()
            total = int(row["total"] or 0) if row else 0

        if total > 0:
            return

        legacy = self._load_legacy_json()
        if legacy:
            self._replace_all_sqlite(legacy)

    def _replace_all_sqlite(self, data):
        normalized = self._normalize_storage(data)
        with get_connection() as connection:
            connection.execute("DELETE FROM role_permissions")
            for guild_id, guild_permissions in normalized.items():
                for role_id, permissions in guild_permissions.items():
                    for permission in permissions:
                        connection.execute(
                            """
                            INSERT INTO role_permissions (guild_id, role_id, permission, created_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (str(guild_id), str(role_id), str(permission), utc_now_iso()),
                        )

    def _replace_guild_permissions_sqlite(self, guild_id, permissions):
        normalized = self.normalize_guild_permissions(permissions)
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                DELETE FROM role_permissions
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            for role_id, values in normalized.items():
                for permission in values:
                    connection.execute(
                        """
                        INSERT INTO role_permissions (guild_id, role_id, permission, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (guild_id, str(role_id), str(permission), now),
                    )
