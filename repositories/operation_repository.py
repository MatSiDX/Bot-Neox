import json
import os

from repositories.balance_repository import DATA_DIR
from repositories.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    normalize_page,
    normalize_page_size,
    page_metadata,
)

OPERATIONS_FILE = os.path.join(DATA_DIR, "operations.json")


class OperationRepository:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(OPERATIONS_FILE):
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
                SELECT guild_id, guild_name, action, operator, operator_id, player, player_id,
                       type, category, amount, previous_balance, new_balance, reason, player_status, date, time
                FROM economy_operations
                ORDER BY guild_id, id
                """
            ).fetchall()

        for row in rows:
            data.setdefault(str(row["guild_id"]), []).append(self._row_to_operation(row))

        return data

    def save(self, data):
        self._save_json(data)

        try:
            self.replace_all(data)
        except ImportError:
            pass

    def _save_json(self, data):
        with open(OPERATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def append(self, guild_id, operation, guild_name=None):
        self._insert(guild_id, operation, guild_name)

    def get_by_guild(self, guild_id):
        from repositories.database import get_connection

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT guild_id, guild_name, action, operator, operator_id, player, player_id,
                       type, category, amount, previous_balance, new_balance, reason, player_status, date, time
                FROM economy_operations
                WHERE guild_id = ?
                ORDER BY id
                """,
                (str(guild_id),),
            ).fetchall()

        return [self._row_to_operation(row) for row in rows]

    def _read_legacy_json(self):
        with open(OPERATIONS_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def _migrate_json_if_empty(self):
        from repositories.database import get_connection

        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM economy_operations").fetchone()[0]

        if count > 0:
            return

        legacy_data = self._read_legacy_json()
        if legacy_data:
            self.replace_all(legacy_data)

    def replace_all(self, data):
        from repositories.database import get_connection

        with get_connection() as connection:
            guild_names = {
                str(row["guild_id"]): row["guild_name"]
                for row in connection.execute(
                    """
                    SELECT guild_id, MAX(guild_name) AS guild_name
                    FROM economy_operations
                    WHERE guild_name IS NOT NULL AND guild_name != ''
                    GROUP BY guild_id
                    """
                ).fetchall()
            }
            connection.execute("DELETE FROM economy_operations")

        for guild_id, operations in data.items():
            if not isinstance(operations, list):
                continue
            for operation in operations:
                if isinstance(operation, dict):
                    self._insert(guild_id, operation, guild_names.get(str(guild_id)))

    def _insert(self, guild_id, operation, guild_name=None):
        from repositories.database import get_connection, utc_now_iso

        stored_guild_name = operation.get("guild_name") or guild_name
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO economy_operations (
                    guild_id, guild_name, action, operator, operator_id, player, player_id,
                    type, category, amount, previous_balance, new_balance, reason, player_status, date, time, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(guild_id),
                    str(stored_guild_name) if stored_guild_name else None,
                    str(operation.get("action", "")),
                    str(operation.get("operator", "")),
                    str(operation.get("operator_id", "")),
                    str(operation.get("player", "")),
                    str(operation.get("player_id", "")),
                    str(operation.get("type", "")),
                    str(operation.get("category", "")),
                    int(operation.get("amount", 0) or 0),
                    operation.get("previous_balance", ""),
                    operation.get("new_balance", ""),
                    str(operation.get("reason", "")),
                    str(operation.get("player_status", "")),
                    str(operation.get("date", "")),
                    str(operation.get("time", "")),
                    utc_now_iso(),
                ),
            )

    def update_guild_name(self, guild_id, guild_name):
        if not guild_id or not guild_name:
            return

        from repositories.database import get_connection

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE economy_operations
                SET guild_name = ?
                WHERE guild_id = ?
                """,
                (str(guild_name), str(guild_id)),
            )

    def _row_to_operation(self, row):
        return {
            "action": row["action"],
            "operator": row["operator"],
            "operator_id": row["operator_id"],
            "player": row["player"],
            "player_id": row["player_id"],
            "type": row["type"],
            "category": row["category"],
            "amount": row["amount"],
            "previous_balance": row["previous_balance"],
            "new_balance": row["new_balance"],
            "reason": row["reason"] if "reason" in row.keys() else "",
            "player_status": row["player_status"] if "player_status" in row.keys() else "",
            "date": row["date"],
            "time": row["time"],
        }

    def list_operations_page(
        self,
        guild_id,
        *,
        page=DEFAULT_PAGE,
        page_size=DEFAULT_PAGE_SIZE,
        search="",
        operation_type="",
        date_from="",
        date_to="",
    ):
        from repositories.database import get_connection

        page = normalize_page(page)
        page_size = normalize_page_size(page_size)
        query = str(search or "").strip().lower()
        operation_type = str(operation_type or "").strip().lower()
        date_from = str(date_from or "").strip()
        date_to = str(date_to or "").strip()

        clauses = ["guild_id = ?"]
        params = [str(guild_id)]
        if query:
            like_query = f"%{query}%"
            clauses.append(
                """
                (
                    LOWER(action) LIKE ?
                    OR LOWER(operator) LIKE ?
                    OR LOWER(operator_id) LIKE ?
                    OR LOWER(player) LIKE ?
                    OR LOWER(player_id) LIKE ?
                    OR LOWER(type) LIKE ?
                    OR LOWER(category) LIKE ?
                    OR LOWER(reason) LIKE ?
                    OR LOWER(player_status) LIKE ?
                )
                """
            )
            params.extend([like_query] * 9)
        if operation_type:
            clauses.append("LOWER(type) = ?")
            params.append(operation_type)
        if date_from:
            clauses.append("date(created_at) >= date(?)")
            params.append(date_from)
        if date_to:
            clauses.append("date(created_at) <= date(?)")
            params.append(date_to)

        where_clause = " AND ".join(clauses)
        with get_connection() as connection:
            total_items = int(
                connection.execute(
                    f"SELECT COUNT(*) AS total_items FROM economy_operations WHERE {where_clause}",
                    params,
                ).fetchone()["total_items"] or 0
            )
            meta = page_metadata(page, page_size, total_items)
            offset = (meta["page"] - 1) * meta["page_size"] if meta["total_pages"] else 0
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    action,
                    operator,
                    operator_id,
                    player,
                    player_id,
                    type,
                    category,
                    amount,
                    previous_balance,
                    new_balance,
                    reason,
                    player_status,
                    date,
                    time,
                    created_at
                FROM economy_operations
                WHERE {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                params + [meta["page_size"], offset],
            ).fetchall()

        meta["items"] = [
            {
                "id": int(row["id"] or 0),
                "action": str(row["action"] or ""),
                "operator": str(row["operator"] or ""),
                "operator_id": str(row["operator_id"] or ""),
                "player": str(row["player"] or ""),
                "player_id": str(row["player_id"] or ""),
                "type": str(row["type"] or ""),
                "category": str(row["category"] or ""),
                "amount": int(row["amount"] or 0),
                "previous_balance": row["previous_balance"],
                "new_balance": row["new_balance"],
                "reason": str(row["reason"] or ""),
                "player_status": str(row["player_status"] or ""),
                "date": str(row["date"] or ""),
                "time": str(row["time"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]
        return meta
