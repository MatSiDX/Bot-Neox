import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "balances.json")


class BalanceRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(DATA_FILE):
            self._save_json({})
        self._init_database()
        self._migrate_json_if_empty()

    def _init_database(self):
        from repositories.database import init_database

        init_database()

    def load(self):
        data = {}
        from repositories.database import get_connection

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT guild_id, guild_name, user_id, user_name, items, silver
                FROM economy_balances
                ORDER BY guild_id, user_id
                """
            ).fetchall()

        for row in rows:
            guild = data.setdefault(str(row["guild_id"]), {})
            user = {
                "items": int(row["items"] or 0),
                "silver": int(row["silver"] or 0),
            }
            if row["user_name"]:
                user["name"] = row["user_name"]
            guild[str(row["user_id"])] = user

        return data

    def save(self, data):
        self._save_json(data)

        try:
            self.replace_all(data)
        except ImportError:
            # database.py imports DATA_DIR from this module during startup.
            pass

    def _save_json(self, data):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def ensure_user(self, data, guild_id, user_id):
        gid = str(guild_id)
        uid = str(user_id)

        if gid not in data:
            data[gid] = {}

        if uid not in data[gid]:
            data[gid][uid] = {"items": 0, "silver": 0}

        return data

    def _read_legacy_json(self):
        with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def _migrate_json_if_empty(self):
        from repositories.database import get_connection

        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM economy_balances").fetchone()[0]

        if count > 0:
            return

        legacy_data = self._read_legacy_json()
        if legacy_data:
            self.replace_all(legacy_data)

    def replace_all(self, data):
        from repositories.database import get_connection, utc_now_iso

        now = utc_now_iso()
        with get_connection() as connection:
            guild_names = {
                str(row["guild_id"]): row["guild_name"]
                for row in connection.execute(
                    """
                    SELECT guild_id, MAX(guild_name) AS guild_name
                    FROM economy_balances
                    WHERE guild_name IS NOT NULL AND guild_name != ''
                    GROUP BY guild_id
                    """
                ).fetchall()
            }
            connection.execute("DELETE FROM economy_balances")
            for guild_id, users in data.items():
                if not isinstance(users, dict):
                    continue
                for user_id, balance in users.items():
                    if not isinstance(balance, dict):
                        continue
                    connection.execute(
                        """
                        INSERT INTO economy_balances (
                            guild_id, guild_name, user_id, user_name, items, silver, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET
                            guild_name = excluded.guild_name,
                            user_name = excluded.user_name,
                            items = excluded.items,
                            silver = excluded.silver,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(guild_id),
                            balance.get("guild_name") or guild_names.get(str(guild_id)),
                            str(user_id),
                            balance.get("name"),
                            int(balance.get("items", 0) or 0),
                            int(balance.get("silver", 0) or 0),
                            now,
                            now,
                        ),
                    )

    def ensure_user_record(self, guild_id, user_id, user_name=None, guild_name=None):
        from repositories.database import get_connection, utc_now_iso

        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO economy_balances (
                    guild_id, guild_name, user_id, user_name, items, silver, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 0, 0, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    guild_name = COALESCE(excluded.guild_name, economy_balances.guild_name),
                    user_name = COALESCE(excluded.user_name, economy_balances.user_name),
                    updated_at = excluded.updated_at
                """,
                (str(guild_id), guild_name, str(user_id), user_name, now, now),
            )

    def get_balance(self, guild_id, user_id, guild_name=None):
        self.ensure_user_record(guild_id, user_id, guild_name=guild_name)

        from repositories.database import get_connection

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT items, silver
                FROM economy_balances
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id)),
            ).fetchone()

        if row is None:
            return 0, 0

        return int(row["items"] or 0), int(row["silver"] or 0)

    def modify_balance(self, guild_id, user_id, amount, key, add=True, guild_name=None):
        if key not in ("items", "silver"):
            raise ValueError("La categoria debe ser 'items' o 'silver'.")

        self.ensure_user_record(guild_id, user_id, guild_name=guild_name)
        delta = int(amount) if add else -int(amount)

        from repositories.database import get_connection, utc_now_iso

        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE economy_balances
                SET {key} = {key} + ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (delta, utc_now_iso(), str(guild_id), str(user_id)),
            )

    def update_user_name(self, guild_id, user_id, user_name, guild_name=None):
        if not user_id or not user_name:
            return

        self.ensure_user_record(guild_id, user_id, user_name, guild_name)

    def update_guild_name(self, guild_id, guild_name):
        if not guild_id or not guild_name:
            return

        from repositories.database import get_connection, utc_now_iso

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE economy_balances
                SET guild_name = ?,
                    updated_at = ?
                WHERE guild_id = ?
                """,
                (str(guild_name), utc_now_iso(), str(guild_id)),
            )

    def get_ranking(self, guild_id, guild_name=None):
        if guild_name:
            self.update_guild_name(guild_id, guild_name)

        from repositories.database import get_connection

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT user_id, items + silver AS total
                FROM economy_balances
                WHERE guild_id = ?
                ORDER BY total DESC, user_id ASC
                """,
                (str(guild_id),),
            ).fetchall()

        return [(int(row["user_id"]), int(row["total"] or 0)) for row in rows]
