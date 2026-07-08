from repositories.database import get_connection, init_database, utc_now_iso


class BotMessageAuditRepository:
    def __init__(self):
        init_database()

    def create(
        self,
        *,
        operator_id,
        operator_name,
        guild_id,
        channel_id,
        action,
        message_id="",
        previous_content="",
        new_content="",
        status="queued",
        error="",
        request_id="",
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO bot_message_audit (
                    operator_id, operator_name, guild_id, channel_id, action,
                    message_id, previous_content, new_content, status, error,
                    request_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(operator_id or ""),
                    str(operator_name or ""),
                    str(guild_id or ""),
                    str(channel_id or ""),
                    str(action or ""),
                    str(message_id or ""),
                    str(previous_content or ""),
                    str(new_content or ""),
                    str(status or "queued"),
                    str(error or ""),
                    str(request_id or ""),
                    now,
                    now,
                ),
            )
            return cursor.lastrowid

    def update_status(self, audit_id, *, status, message_id="", previous_content=None, error=""):
        if not audit_id:
            return None

        now = utc_now_iso()
        assignments = [
            "status = ?",
            "error = ?",
            "updated_at = ?",
        ]
        params = [str(status or ""), str(error or ""), now]
        if message_id:
            assignments.append("message_id = ?")
            params.append(str(message_id))
        if previous_content is not None:
            assignments.append("previous_content = ?")
            params.append(str(previous_content or ""))

        params.append(int(audit_id))
        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE bot_message_audit
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                params,
            )
        return self.get(audit_id)

    def attach_request(self, audit_id, request_id):
        if not audit_id:
            return None

        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE bot_message_audit
                SET request_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(request_id or ""), now, int(audit_id)),
            )
        return self.get(audit_id)

    def get(self, audit_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM bot_message_audit
                WHERE id = ?
                """,
                (int(audit_id),),
            ).fetchone()
        return dict(row) if row else None
