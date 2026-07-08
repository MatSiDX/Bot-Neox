import json

from repositories.database import get_connection, init_database, utc_now_iso


class ServerTemplateRestoreRepository:
    def __init__(self):
        init_database()

    def create(
        self,
        *,
        backup_id,
        source_guild_id,
        source_guild_name,
        target_guild_id,
        target_guild_name,
        operator_id,
        operator_name,
        options,
        preview,
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO server_template_restores (
                    backup_id, source_guild_id, source_guild_name,
                    target_guild_id, target_guild_name, operator_id, operator_name,
                    status, options_json, preview_json, id_map_json, result_json,
                    error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, '{}', '{}', '', ?, ?)
                """,
                (
                    int(backup_id),
                    str(source_guild_id or ""),
                    str(source_guild_name or ""),
                    str(target_guild_id or ""),
                    str(target_guild_name or ""),
                    str(operator_id or ""),
                    str(operator_name or ""),
                    self._json_dumps(options or {}),
                    self._json_dumps(preview or {}),
                    now,
                    now,
                ),
            )
            restore_id = int(cursor.lastrowid)
        return self.get(restore_id)

    def attach_request(self, restore_id, request_id):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE server_template_restores
                SET request_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(request_id or ""), now, int(restore_id)),
            )
        return self.get(restore_id)

    def mark_completed(self, restore_id, *, id_map=None, result=None):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE server_template_restores
                SET status = 'completed',
                    id_map_json = ?,
                    result_json = ?,
                    error = '',
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    self._json_dumps(id_map or {}),
                    self._json_dumps(result or {}),
                    now,
                    now,
                    int(restore_id),
                ),
            )
        return self.get(restore_id)

    def mark_failed(self, restore_id, *, error, id_map=None, result=None):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE server_template_restores
                SET status = 'failed',
                    id_map_json = ?,
                    result_json = ?,
                    error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    self._json_dumps(id_map or {}),
                    self._json_dumps(result or {}),
                    str(error or "")[:1000],
                    now,
                    int(restore_id),
                ),
            )
        return self.get(restore_id)

    def get(self, restore_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM server_template_restores
                WHERE id = ?
                """,
                (int(restore_id),),
            ).fetchone()
        return self._row_to_dict(row)

    def get_by_request_id(self, request_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM server_template_restores
                WHERE request_id = ?
                """,
                (str(request_id or ""),),
            ).fetchone()
        return self._row_to_dict(row)

    def _row_to_dict(self, row):
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "request_id": str(row["request_id"] or ""),
            "backup_id": int(row["backup_id"] or 0),
            "source_guild_id": str(row["source_guild_id"] or ""),
            "source_guild_name": str(row["source_guild_name"] or ""),
            "target_guild_id": str(row["target_guild_id"] or ""),
            "target_guild_name": str(row["target_guild_name"] or ""),
            "operator_id": str(row["operator_id"] or ""),
            "operator_name": str(row["operator_name"] or ""),
            "status": str(row["status"] or ""),
            "options": self._json_loads(row["options_json"], {}),
            "preview": self._json_loads(row["preview_json"], {}),
            "id_map": self._json_loads(row["id_map_json"], {}),
            "result": self._json_loads(row["result_json"], {}),
            "error": str(row["error"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
        }

    @staticmethod
    def _json_dumps(value):
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _json_loads(value, default):
        try:
            parsed = json.loads(value or "")
            return parsed if isinstance(parsed, type(default)) else default
        except (TypeError, ValueError):
            return default
