import json
import os
import re
from numbers import Integral

from config.settings import DATA_DIR
from repositories.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    normalize_page,
    normalize_page_size,
    page_metadata,
)

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

    def _normalize_amount(self, amount):
        if amount is None or isinstance(amount, bool):
            raise ValueError("La cantidad debe ser un numero entero valido.")

        if isinstance(amount, Integral):
            normalized = int(amount)
        elif isinstance(amount, str):
            value = amount.strip()
            if not re.fullmatch(r"[+-]?\d+", value):
                raise ValueError("La cantidad debe ser un numero entero valido.")
            normalized = int(value)
        else:
            raise ValueError("La cantidad debe ser un numero entero valido.")

        if normalized == 0:
            raise ValueError("La cantidad debe ser distinta de 0.")

        return normalized

    def _normalize_lookup_text(self, value):
        return " ".join(str(value or "").strip().lower().split())

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

    def get_balance_record(self, guild_id, user_id):
        from repositories.database import get_connection

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT guild_id, guild_name, user_id, user_name, items, silver, created_at, updated_at
                FROM economy_balances
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id)),
            ).fetchone()

        if row is None:
            return None

        return {
            "guild_id": str(row["guild_id"] or ""),
            "guild_name": str(row["guild_name"] or ""),
            "user_id": str(row["user_id"] or ""),
            "user_name": str(row["user_name"] or ""),
            "items": int(row["items"] or 0),
            "silver": int(row["silver"] or 0),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def resolve_existing_user(self, guild_id, identifier):
        query = self._normalize_lookup_text(identifier)
        if not query:
            return None

        from repositories.database import get_connection

        exact_params = (str(guild_id), query)
        like_query = f"%{query}%"
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT b.*, 'discord_id' AS matched_by, b.user_id AS internal_id
                FROM economy_balances b
                WHERE b.guild_id = ? AND LOWER(b.user_id) = ?
                LIMIT 1
                """,
                exact_params,
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT b.*, 'balance_name' AS matched_by, b.user_id AS internal_id
                    FROM economy_balances b
                    WHERE b.guild_id = ?
                      AND LOWER(COALESCE(b.user_name, '')) = ?
                    ORDER BY b.updated_at DESC
                    LIMIT 1
                    """,
                    exact_params,
                ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT b.*, 'operation_name' AS matched_by, o.id AS internal_id
                    FROM economy_balances b
                    JOIN economy_operations o
                      ON o.guild_id = b.guild_id
                     AND o.player_id = b.user_id
                    WHERE b.guild_id = ?
                      AND LOWER(COALESCE(o.player, '')) = ?
                    ORDER BY o.id DESC
                    LIMIT 1
                    """,
                    exact_params,
                ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT b.*, 'albion_registration' AS matched_by, r.player_id AS internal_id
                    FROM economy_balances b
                    JOIN albion_registrations r
                      ON r.guild_id = b.guild_id
                     AND r.discord_user_id = b.user_id
                    WHERE b.guild_id = ?
                      AND (
                        LOWER(r.discord_user_id) = ?
                        OR LOWER(COALESCE(r.discord_user_name, '')) = ?
                        OR LOWER(COALESCE(r.player_id, '')) = ?
                        OR LOWER(COALESCE(r.player_name, '')) = ?
                        OR LOWER(COALESCE(r.original_nickname, '')) = ?
                      )
                    ORDER BY r.updated_at DESC
                    LIMIT 1
                    """,
                    (str(guild_id), query, query, query, query, query),
                ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT b.*, 'partial_match' AS matched_by, b.user_id AS internal_id
                    FROM economy_balances b
                    WHERE b.guild_id = ?
                      AND (
                        LOWER(b.user_id) LIKE ?
                        OR LOWER(COALESCE(b.user_name, '')) LIKE ?
                      )
                    ORDER BY b.updated_at DESC
                    LIMIT 1
                    """,
                    (str(guild_id), like_query, like_query),
                ).fetchone()

        if row is None:
            return None

        result = self.get_balance_record(guild_id, row["user_id"])
        if result:
            result["matched_by"] = str(row["matched_by"] or "")
            result["internal_id"] = str(row["internal_id"] or "")
        return result

    def search_existing_users(self, guild_id, query, limit=25):
        normalized = self._normalize_lookup_text(query)
        if not normalized:
            return []

        from repositories.database import get_connection

        like_query = f"%{normalized}%"
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    b.user_id,
                    COALESCE(
                        NULLIF(b.user_name, ''),
                        (
                            SELECT NULLIF(player, '')
                            FROM economy_operations
                            WHERE guild_id = b.guild_id
                              AND player_id = b.user_id
                              AND NULLIF(player, '') IS NOT NULL
                            ORDER BY id DESC
                            LIMIT 1
                        ),
                        r.player_name,
                        ''
                    ) AS user_name,
                    b.items,
                    b.silver,
                    r.player_id AS internal_id
                FROM economy_balances b
                LEFT JOIN albion_registrations r
                  ON r.guild_id = b.guild_id
                 AND r.discord_user_id = b.user_id
                WHERE b.guild_id = ?
                  AND (
                    LOWER(b.user_id) LIKE ?
                    OR LOWER(COALESCE(b.user_name, '')) LIKE ?
                    OR LOWER(COALESCE(r.discord_user_name, '')) LIKE ?
                    OR LOWER(COALESCE(r.player_id, '')) LIKE ?
                    OR LOWER(COALESCE(r.player_name, '')) LIKE ?
                    OR LOWER(COALESCE(r.original_nickname, '')) LIKE ?
                  )
                ORDER BY (b.items + b.silver) DESC, user_name COLLATE NOCASE, b.user_id
                LIMIT ?
                """,
                (str(guild_id), like_query, like_query, like_query, like_query, like_query, like_query, int(limit)),
            ).fetchall()

        return [
            {
                "user_id": str(row["user_id"] or ""),
                "user_name": str(row["user_name"] or ""),
                "internal_id": str(row["internal_id"] or ""),
                "items": int(row["items"] or 0),
                "silver": int(row["silver"] or 0),
            }
            for row in rows
        ]

    def modify_balance(self, guild_id, user_id, amount, key, add=True, guild_name=None):
        if key not in ("items", "silver"):
            raise ValueError("La categoria debe ser 'items' o 'silver'.")

        self.ensure_user_record(guild_id, user_id, guild_name=guild_name)
        normalized_amount = self._normalize_amount(amount)
        delta = normalized_amount if add else -normalized_amount

        from repositories.database import get_connection, utc_now_iso

        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT {key}
                FROM economy_balances
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id)),
            ).fetchone()
            current_value = int(row[key] or 0) if row is not None else 0
            new_value = current_value + delta

            connection.execute(
                f"""
                UPDATE economy_balances
                SET {key} = {key} + ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (delta, utc_now_iso(), str(guild_id), str(user_id)),
            )

        return new_value

    def modify_existing_balance(self, guild_id, user_id, amount, key, add=True):
        if key not in ("items", "silver"):
            raise ValueError("La categoria debe ser 'items' o 'silver'.")

        normalized_amount = self._normalize_amount(amount)
        delta = normalized_amount if add else -normalized_amount

        from repositories.database import get_connection, utc_now_iso

        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT items, silver
                FROM economy_balances
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id)),
            ).fetchone()
            if row is None:
                raise LookupError("El usuario no existe en la base de datos de economia.")

            previous_value = int(row[key] or 0)
            new_value = previous_value + delta
            connection.execute(
                f"""
                UPDATE economy_balances
                SET {key} = ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (new_value, utc_now_iso(), str(guild_id), str(user_id)),
            )

        return previous_value, new_value

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

    def get_dashboard_summary(self, guild_id):
        from repositories.database import get_connection

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS players,
                    COALESCE(SUM(items), 0) AS items,
                    COALESCE(SUM(silver), 0) AS silver
                FROM economy_balances
                WHERE guild_id = ?
                """,
                (str(guild_id),),
            ).fetchone()

        players = int(row["players"] or 0) if row else 0
        items = int(row["items"] or 0) if row else 0
        silver = int(row["silver"] or 0) if row else 0
        return {
            "players": players,
            "items": items,
            "silver": silver,
            "total": items + silver,
        }

    def list_balances_page(self, guild_id, *, page=DEFAULT_PAGE, page_size=DEFAULT_PAGE_SIZE, search=""):
        from repositories.database import get_connection

        page = normalize_page(page)
        page_size = normalize_page_size(page_size)
        query = str(search or "").strip()
        like_query = f"%{query.lower()}%" if query else ""
        search_clause = ""
        params = [str(guild_id)]
        search_params = []
        if like_query:
            search_clause = """
                AND (
                    LOWER(user_id) LIKE ?
                    OR LOWER(
                        COALESCE(
                            NULLIF(user_name, ''),
                            (
                                SELECT NULLIF(player, '')
                                FROM economy_operations
                                WHERE guild_id = economy_balances.guild_id
                                  AND player_id = economy_balances.user_id
                                  AND NULLIF(player, '') IS NOT NULL
                                  AND player != 'Usuario ' || economy_balances.user_id
                                ORDER BY id DESC
                                LIMIT 1
                            ),
                            (
                                SELECT NULLIF(operator, '')
                                FROM economy_operations
                                WHERE guild_id = economy_balances.guild_id
                                  AND operator_id = economy_balances.user_id
                                  AND NULLIF(operator, '') IS NOT NULL
                                  AND operator != 'Usuario ' || economy_balances.user_id
                                ORDER BY id DESC
                                LIMIT 1
                            ),
                            ''
                        )
                    ) LIKE ?
                )
            """
            search_params = [like_query, like_query]

        count_query = f"""
            SELECT COUNT(*) AS total_items
            FROM economy_balances
            WHERE guild_id = ?
            {search_clause}
        """

        with get_connection() as connection:
            total_items = int(
                connection.execute(count_query, params + search_params).fetchone()["total_items"] or 0
            )
            meta = page_metadata(page, page_size, total_items)
            offset = (meta["page"] - 1) * meta["page_size"] if meta["total_pages"] else 0
            rows = connection.execute(
                f"""
                SELECT
                    user_id,
                    COALESCE(
                        NULLIF(user_name, ''),
                        (
                            SELECT NULLIF(player, '')
                            FROM economy_operations
                            WHERE guild_id = economy_balances.guild_id
                              AND player_id = economy_balances.user_id
                              AND NULLIF(player, '') IS NOT NULL
                              AND player != 'Usuario ' || economy_balances.user_id
                            ORDER BY id DESC
                            LIMIT 1
                        ),
                        (
                            SELECT NULLIF(operator, '')
                            FROM economy_operations
                            WHERE guild_id = economy_balances.guild_id
                              AND operator_id = economy_balances.user_id
                              AND NULLIF(operator, '') IS NOT NULL
                              AND operator != 'Usuario ' || economy_balances.user_id
                            ORDER BY id DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS user_name,
                    items,
                    silver,
                    items + silver AS total,
                    updated_at
                FROM economy_balances
                WHERE guild_id = ?
                {search_clause}
                ORDER BY total DESC, user_name COLLATE NOCASE, user_id
                LIMIT ? OFFSET ?
                """,
                params + search_params + [meta["page_size"], offset],
            ).fetchall()

        items = []
        start_rank = offset + 1
        for index, row in enumerate(rows, start=start_rank):
            items.append({
                "rank": index,
                "user_id": str(row["user_id"] or ""),
                "user_name": str(row["user_name"] or ""),
                "items": int(row["items"] or 0),
                "silver": int(row["silver"] or 0),
                "total": int(row["total"] or 0),
                "updated_at": str(row["updated_at"] or ""),
            })
        meta["items"] = items
        return meta
