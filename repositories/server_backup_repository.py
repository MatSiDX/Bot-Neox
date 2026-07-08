import json

from repositories.database import get_connection, init_database, utc_now_iso


MAX_SERVER_BACKUPS = 2


class ServerBackupLimitError(RuntimeError):
    def __init__(self, backups):
        super().__init__("El servidor ya tiene el maximo de backups permitidos.")
        self.backups = backups


class ServerBackupRepository:
    def __init__(self):
        init_database()

    def list_for_guild(self, guild_id):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, guild_id, guild_name, created_by_id, created_by_name,
                       schema_version, summary_json, created_at
                FROM server_backups
                WHERE guild_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (str(guild_id or ""),),
            ).fetchall()
        return [self._row_to_summary(row) for row in rows]

    def get(self, backup_id, *, guild_id=None):
        params = [int(backup_id)]
        guild_filter = ""
        if guild_id is not None:
            guild_filter = " AND guild_id = ?"
            params.append(str(guild_id or ""))

        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT *
                FROM server_backups
                WHERE id = ?{guild_filter}
                """,
                params,
            ).fetchone()
        return self._row_to_detail(row) if row else None

    def create(
        self,
        *,
        guild_id,
        guild_name,
        created_by_id,
        created_by_name,
        schema_version,
        backup,
        summary,
        replace_oldest=False,
        replace_backup_id=None,
    ):
        guild_id = str(guild_id or "")
        now = utc_now_iso()
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, guild_id, guild_name, created_by_id, created_by_name,
                       schema_version, summary_json, created_at
                FROM server_backups
                WHERE guild_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (guild_id,),
            ).fetchall()

            if len(rows) >= MAX_SERVER_BACKUPS:
                summaries = [self._row_to_summary(row) for row in rows]
                backup_id_to_delete = self._resolve_backup_to_replace(
                    rows,
                    replace_oldest=replace_oldest,
                    replace_backup_id=replace_backup_id,
                )
                if backup_id_to_delete is None:
                    raise ServerBackupLimitError(summaries)
                connection.execute("DELETE FROM server_backups WHERE id = ?", (backup_id_to_delete,))

            cursor = connection.execute(
                """
                INSERT INTO server_backups (
                    guild_id, guild_name, created_by_id, created_by_name,
                    schema_version, backup_json, summary_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    str(guild_name or ""),
                    str(created_by_id or ""),
                    str(created_by_name or ""),
                    int(schema_version or 1),
                    json.dumps(backup or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(summary or {}, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            backup_id = cursor.lastrowid

        return self.get(backup_id, guild_id=guild_id)

    def _resolve_backup_to_replace(self, rows, *, replace_oldest=False, replace_backup_id=None):
        if replace_backup_id not in (None, ""):
            try:
                requested_id = int(replace_backup_id)
            except (TypeError, ValueError):
                return None
            row_ids = {int(row["id"]) for row in rows}
            return requested_id if requested_id in row_ids else None

        if replace_oldest:
            return int(rows[0]["id"])

        return None

    def _row_to_summary(self, row):
        if not row:
            return None
        summary = self._json_loads(row["summary_json"], {})
        return {
            "id": int(row["id"]),
            "guild_id": str(row["guild_id"] or ""),
            "guild_name": str(row["guild_name"] or ""),
            "created_by_id": str(row["created_by_id"] or ""),
            "created_by_name": str(row["created_by_name"] or ""),
            "schema_version": int(row["schema_version"] or 1),
            "summary": summary,
            "created_at": str(row["created_at"] or ""),
        }

    def _row_to_detail(self, row):
        if not row:
            return None
        payload = self._row_to_summary(row)
        payload["backup"] = self._json_loads(row["backup_json"], {})
        return payload

    @staticmethod
    def _json_loads(value, default):
        try:
            parsed = json.loads(value or "")
            return parsed if isinstance(parsed, type(default)) else default
        except (TypeError, ValueError):
            return default
