import json

from repositories.database import get_connection, init_database, utc_now_iso


def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value):
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class DashboardAdminSecurityRepository:
    def __init__(self):
        init_database()

    def get_attempt(self, subject_type, subject_key):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM dashboard_admin_auth_attempts
                WHERE subject_type = ? AND subject_key = ?
                """,
                (str(subject_type or ""), str(subject_key or "")),
            ).fetchone()
        return self._serialize_attempt(row)

    def save_attempt(
        self,
        *,
        subject_type,
        subject_key,
        failures,
        first_failure_at="",
        last_failure_at="",
        locked_until="",
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO dashboard_admin_auth_attempts (
                    subject_type,
                    subject_key,
                    failures,
                    first_failure_at,
                    last_failure_at,
                    locked_until,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject_type, subject_key) DO UPDATE SET
                    failures = excluded.failures,
                    first_failure_at = excluded.first_failure_at,
                    last_failure_at = excluded.last_failure_at,
                    locked_until = excluded.locked_until,
                    updated_at = excluded.updated_at
                """,
                (
                    str(subject_type or ""),
                    str(subject_key or ""),
                    max(0, int(failures or 0)),
                    str(first_failure_at or ""),
                    str(last_failure_at or ""),
                    str(locked_until or ""),
                    now,
                    now,
                ),
            )
        return self.get_attempt(subject_type, subject_key)

    def clear_attempt(self, subject_type, subject_key):
        with get_connection() as connection:
            connection.execute(
                """
                DELETE FROM dashboard_admin_auth_attempts
                WHERE subject_type = ? AND subject_key = ?
                """,
                (str(subject_type or ""), str(subject_key or "")),
            )

    def append_audit_event(
        self,
        *,
        event_type,
        actor_user_id="",
        actor_name="",
        ip_address="",
        details=None,
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO dashboard_admin_audit_events (
                    event_type,
                    actor_user_id,
                    actor_name,
                    ip_address,
                    details_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_type or ""),
                    str(actor_user_id or ""),
                    str(actor_name or ""),
                    str(ip_address or ""),
                    _json_dumps(details),
                    now,
                ),
            )
        return self.get_audit_event(cursor.lastrowid)

    def get_audit_event(self, event_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM dashboard_admin_audit_events
                WHERE id = ?
                """,
                (int(event_id),),
            ).fetchone()
        return self._serialize_audit(row)

    def list_audit_events(self, limit=100):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM dashboard_admin_audit_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, int(limit or 100)),),
            ).fetchall()
        return [self._serialize_audit(row) for row in rows]

    def _serialize_attempt(self, row):
        if row is None:
            return None
        return {
            "subject_type": str(row["subject_type"] or ""),
            "subject_key": str(row["subject_key"] or ""),
            "failures": int(row["failures"] or 0),
            "first_failure_at": str(row["first_failure_at"] or ""),
            "last_failure_at": str(row["last_failure_at"] or ""),
            "locked_until": str(row["locked_until"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def _serialize_audit(self, row):
        if row is None:
            return None
        return {
            "id": int(row["id"] or 0),
            "event_type": str(row["event_type"] or ""),
            "actor_user_id": str(row["actor_user_id"] or ""),
            "actor_name": str(row["actor_name"] or ""),
            "ip_address": str(row["ip_address"] or ""),
            "details": _json_loads(row["details_json"]),
            "created_at": str(row["created_at"] or ""),
        }
