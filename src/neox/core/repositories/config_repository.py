import os

from repositories.database import get_connection, init_database, utc_now_iso
from src.neox.config.settings import DATA_DIR
from utils.json_store import mutate_json, read_json, write_json


CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


class ConfigRepository:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(CONFIG_FILE):
            write_json(CONFIG_FILE, {})
        init_database()
        self._migrate_json_if_needed()

    def load(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT guild_id, key, value
                FROM guild_config
                ORDER BY guild_id, key
                """
            ).fetchall()

        if rows:
            data = {}
            for row in rows:
                data.setdefault(str(row["guild_id"]), {})[str(row["key"])] = str(row["value"])
            return data

        return self._load_legacy_json()

    def save(self, data):
        normalized = self._normalize_storage(data)
        write_json(CONFIG_FILE, normalized)
        self._replace_all_sqlite(normalized)

    def get_guild_config(self, guild_id):
        guild_id = str(guild_id)
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT key, value
                FROM guild_config
                WHERE guild_id = ?
                ORDER BY key
                """,
                (guild_id,),
            ).fetchall()

        if rows:
            return {
                str(row["key"]): str(row["value"])
                for row in rows
            }

        data = self._load_legacy_json()
        legacy = data.get(guild_id, {})
        if isinstance(legacy, dict) and legacy:
            self._upsert_many_sqlite(guild_id, legacy)
            return dict(legacy)
        return {}

    def set_value(self, guild_id, key, value):
        guild_id = str(guild_id)
        key = str(key)
        value = None if value in (None, "") else str(value)
        self._set_value_sqlite(guild_id, key, value)

        def mutate(data):
            data = self._normalize_storage(data)
            if guild_id not in data:
                data[guild_id] = {}

            if value is None:
                data[guild_id].pop(key, None)
                if not data[guild_id]:
                    data.pop(guild_id, None)
            else:
                data[guild_id][key] = value
            return data

        mutate_json(CONFIG_FILE, {}, mutate)

    def set_channel(self, guild_id, channel_type, channel_id):
        self.set_value(guild_id, channel_type, channel_id)

    def _load_legacy_json(self):
        data = read_json(CONFIG_FILE, {})
        return self._normalize_storage(data)

    def _normalize_storage(self, data):
        if not isinstance(data, dict):
            return {}

        normalized = {}
        for guild_id, guild_config in data.items():
            if not isinstance(guild_config, dict):
                continue
            clean_guild_config = {}
            for key, value in guild_config.items():
                if value in (None, ""):
                    continue
                clean_guild_config[str(key)] = str(value)
            if clean_guild_config:
                normalized[str(guild_id)] = clean_guild_config
        return normalized

    def _migrate_json_if_needed(self):
        with get_connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM guild_config").fetchone()
            total = int(row["total"] or 0) if row else 0

        if total > 0:
            return

        legacy = self._load_legacy_json()
        if legacy:
            self._replace_all_sqlite(legacy)

    def _replace_all_sqlite(self, data):
        normalized = self._normalize_storage(data)
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute("DELETE FROM guild_config")
            for guild_id, guild_config in normalized.items():
                for key, value in guild_config.items():
                    connection.execute(
                        """
                        INSERT INTO guild_config (guild_id, key, value, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (str(guild_id), str(key), str(value), now, now),
                    )

    def _upsert_many_sqlite(self, guild_id, values):
        now = utc_now_iso()
        with get_connection() as connection:
            for key, value in values.items():
                if value in (None, ""):
                    continue
                connection.execute(
                    """
                    INSERT INTO guild_config (guild_id, key, value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (str(guild_id), str(key), str(value), now, now),
                )

    def _set_value_sqlite(self, guild_id, key, value):
        now = utc_now_iso()
        with get_connection() as connection:
            if value is None:
                connection.execute(
                    """
                    DELETE FROM guild_config
                    WHERE guild_id = ? AND key = ?
                    """,
                    (guild_id, key),
                )
                return

            connection.execute(
                """
                INSERT INTO guild_config (guild_id, key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (guild_id, key, value, now, now),
            )
