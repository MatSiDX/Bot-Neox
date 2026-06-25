from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from repositories.database import get_connection, init_database, utc_now_iso


def _json_dumps(value):
    if value in (None, "", {}):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


class DashboardActionRequestRepository:
    def __init__(self):
        init_database()

    def create(
        self,
        *,
        guild_id,
        action_type,
        payload,
        requested_by="",
        max_retries=3,
        idempotency_key=None,
        correlation_id="",
    ):
        request_id = secrets.token_urlsafe(12)
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO dashboard_action_requests (
                    id, guild_id, action_type, payload_json, status,
                    requested_by, result_json, error, created_at, updated_at,
                    processed_at, retry_count, max_retries, next_retry_at,
                    locked_by, locked_at, idempotency_key, correlation_id
                )
                VALUES (?, ?, ?, ?, 'pending', ?, '', '', ?, ?, '', 0, ?, '', '', '', ?, ?)
                """,
                (
                    request_id,
                    str(guild_id or ""),
                    str(action_type or ""),
                    _json_dumps(payload) or "{}",
                    str(requested_by or ""),
                    now,
                    now,
                    max(0, int(max_retries or 0)),
                    str(idempotency_key) if idempotency_key else None,
                    str(correlation_id or ""),
                ),
            )
        return self.get(request_id)

    def get(self, request_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM dashboard_action_requests
                WHERE id = ?
                """,
                (str(request_id or ""),),
            ).fetchone()
        return self._serialize_row(row)

    def get_by_idempotency_key(self, idempotency_key):
        if not idempotency_key:
            return None
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM dashboard_action_requests
                WHERE idempotency_key = ?
                """,
                (str(idempotency_key),),
            ).fetchone()
        return self._serialize_row(row)

    def claim_next(self, worker_id, *, action_types=None):
        worker_id = str(worker_id or "").strip()
        if not worker_id:
            raise ValueError("worker_id es obligatorio para reclamar solicitudes.")

        action_types = [str(item).strip() for item in (action_types or []) if str(item).strip()]
        now = utc_now_iso()
        clauses = [
            "status IN ('pending', 'retry')",
            "(next_retry_at = '' OR next_retry_at <= ?)",
            "locked_at = ''",
        ]
        params = [now]
        if action_types:
            placeholders = ", ".join("?" for _ in action_types)
            clauses.append(f"action_type IN ({placeholders})")
            params.extend(action_types)

        where_clause = " AND ".join(clauses)
        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT id
                FROM dashboard_action_requests
                WHERE {where_clause}
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
                ,
                params,
            ).fetchone()
            if not row:
                return None

            request_id = str(row["id"])
            cursor = connection.execute(
                """
                UPDATE dashboard_action_requests
                SET status = 'processing',
                    locked_by = ?,
                    locked_at = ?,
                    updated_at = ?,
                    next_retry_at = ''
                WHERE id = ?
                  AND status IN ('pending', 'retry')
                  AND locked_at = ''
                """,
                (worker_id, now, now, request_id),
            )
            if cursor.rowcount != 1:
                return None

            claimed = connection.execute(
                """
                SELECT *
                FROM dashboard_action_requests
                WHERE id = ?
                """,
                (request_id,),
            ).fetchone()
        return self._serialize_row(claimed)

    def mark_completed(self, request_id, *, result=None):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE dashboard_action_requests
                SET status = 'completed',
                    result_json = ?,
                    error = '',
                    processed_at = ?,
                    updated_at = ?,
                    locked_by = '',
                    locked_at = ''
                WHERE id = ?
                """,
                (_json_dumps(result), now, now, str(request_id or "")),
            )
        return self.get(request_id)

    def mark_retry(self, request_id, *, error, result=None, retry_delay_seconds=30):
        current = self.get(request_id)
        if not current:
            return None

        next_retry_count = int(current.get("retry_count") or 0) + 1
        next_retry_at = (
            datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=max(1, int(retry_delay_seconds or 30)))
        ).isoformat().replace("+00:00", "Z")
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE dashboard_action_requests
                SET status = 'retry',
                    retry_count = ?,
                    result_json = ?,
                    error = ?,
                    next_retry_at = ?,
                    updated_at = ?,
                    locked_by = '',
                    locked_at = ''
                WHERE id = ?
                """,
                (
                    next_retry_count,
                    _json_dumps(result),
                    str(error or "")[:1000],
                    next_retry_at,
                    now,
                    str(request_id or ""),
                ),
            )
        return self.get(request_id)

    def mark_failed(self, request_id, *, error, result=None):
        current = self.get(request_id)
        if not current:
            return None

        next_retry_count = int(current.get("retry_count") or 0) + 1
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE dashboard_action_requests
                SET status = 'failed',
                    retry_count = ?,
                    result_json = ?,
                    error = ?,
                    processed_at = ?,
                    next_retry_at = '',
                    updated_at = ?,
                    locked_by = '',
                    locked_at = ''
                WHERE id = ?
                """,
                (
                    next_retry_count,
                    _json_dumps(result),
                    str(error or "")[:1000],
                    now,
                    now,
                    str(request_id or ""),
                ),
            )
        return self.get(request_id)

    def list_requests(self, *, statuses=None, action_types=None, limit=100):
        clauses = ["1 = 1"]
        params = []
        if statuses:
            clean_statuses = [str(item).strip() for item in statuses if str(item).strip()]
            if clean_statuses:
                placeholders = ", ".join("?" for _ in clean_statuses)
                clauses.append(f"status IN ({placeholders})")
                params.extend(clean_statuses)
        if action_types:
            clean_action_types = [str(item).strip() for item in action_types if str(item).strip()]
            if clean_action_types:
                placeholders = ", ".join("?" for _ in clean_action_types)
                clauses.append(f"action_type IN ({placeholders})")
                params.extend(clean_action_types)

        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM dashboard_action_requests
                WHERE {" AND ".join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params + [max(1, int(limit or 100))],
            ).fetchall()
        return [self._serialize_row(row) for row in rows]

    def _serialize_row(self, row):
        if row is None:
            return None

        payload = _json_loads(row["payload_json"])
        result = _json_loads(row["result_json"])
        return {
            "id": str(row["id"] or ""),
            "guild_id": str(row["guild_id"] or ""),
            "action_type": str(row["action_type"] or ""),
            "payload_json": str(row["payload_json"] or ""),
            "payload": payload if isinstance(payload, (dict, list)) else payload,
            "status": str(row["status"] or "pending"),
            "requested_by": str(row["requested_by"] or ""),
            "result_json": str(row["result_json"] or ""),
            "result": result if isinstance(result, (dict, list)) else result,
            "error": str(row["error"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "processed_at": str(row["processed_at"] or ""),
            "retry_count": int(row["retry_count"] or 0),
            "max_retries": int(row["max_retries"] or 0),
            "next_retry_at": str(row["next_retry_at"] or ""),
            "locked_by": str(row["locked_by"] or ""),
            "locked_at": str(row["locked_at"] or ""),
            "idempotency_key": str(row["idempotency_key"] or ""),
            "correlation_id": str(row["correlation_id"] or ""),
        }
