from repositories.database import get_connection, utc_now_iso
from repositories.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    normalize_page,
    normalize_page_size,
    page_metadata,
)


class FineRepository:
    def create(self, payload):
        now = utc_now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO economy_fines (
                    guild_id, guild_name, report_ava, fined_user_id, fined_user_name,
                    amount, reason, proof_path, proof_name, status,
                    blocked_role_id, resolver_role_id, ticket_channel_id, ticket_message_id,
                    announcement_channel_id, announcement_message_id,
                    created_by_id, created_by_name, paid_by_id, paid_by_name,
                    created_at, updated_at, paid_at, closed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, '', '')
                """,
                (
                    str(payload.get("guild_id") or ""),
                    payload.get("guild_name"),
                    str(payload.get("report_ava") or ""),
                    str(payload.get("fined_user_id") or ""),
                    str(payload.get("fined_user_name") or ""),
                    int(payload.get("amount") or 0),
                    str(payload.get("reason") or ""),
                    str(payload.get("proof_path") or ""),
                    str(payload.get("proof_name") or ""),
                    str(payload.get("status") or "open"),
                    str(payload.get("blocked_role_id") or ""),
                    str(payload.get("resolver_role_id") or ""),
                    str(payload.get("ticket_channel_id") or ""),
                    str(payload.get("ticket_message_id") or ""),
                    str(payload.get("announcement_channel_id") or ""),
                    str(payload.get("announcement_message_id") or ""),
                    str(payload.get("created_by_id") or ""),
                    str(payload.get("created_by_name") or ""),
                    now,
                    now,
                ),
            )
            fine_id = int(cursor.lastrowid or 0)
        return self.get(fine_id)

    def get(self, fine_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM economy_fines
                WHERE id = ?
                """,
                (int(fine_id or 0),),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_by_guild(self, guild_id):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM economy_fines
                WHERE guild_id = ?
                ORDER BY id DESC
                """,
                (str(guild_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_open(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM economy_fines
                WHERE status = 'open'
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_unpaid_by_user(self, guild_id, user_id):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM economy_fines
                WHERE guild_id = ? AND fined_user_id = ? AND status = 'open'
                ORDER BY id DESC
                """,
                (str(guild_id), str(user_id)),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_channels(self, fine_id, *, ticket_channel_id=None, ticket_message_id=None, announcement_channel_id=None, announcement_message_id=None):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE economy_fines
                SET ticket_channel_id = COALESCE(?, ticket_channel_id),
                    ticket_message_id = COALESCE(?, ticket_message_id),
                    announcement_channel_id = COALESCE(?, announcement_channel_id),
                    announcement_message_id = COALESCE(?, announcement_message_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(ticket_channel_id) if ticket_channel_id is not None else None,
                    str(ticket_message_id) if ticket_message_id is not None else None,
                    str(announcement_channel_id) if announcement_channel_id is not None else None,
                    str(announcement_message_id) if announcement_message_id is not None else None,
                    now,
                    int(fine_id or 0),
                ),
            )
        return self.get(fine_id)

    def mark_paid(self, fine_id, *, paid_by_id, paid_by_name):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE economy_fines
                SET status = 'paid',
                    paid_by_id = ?,
                    paid_by_name = ?,
                    paid_at = ?,
                    closed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(paid_by_id or ""),
                    str(paid_by_name or ""),
                    now,
                    now,
                    now,
                    int(fine_id or 0),
                ),
            )
        return self.get(fine_id)

    def list_by_guild_page(
        self,
        guild_id,
        *,
        page=DEFAULT_PAGE,
        page_size=DEFAULT_PAGE_SIZE,
        search="",
        status="",
        record_type="",
        date_from="",
        date_to="",
    ):
        page = normalize_page(page)
        page_size = normalize_page_size(page_size)
        query = str(search or "").strip().lower()
        status = str(status or "").strip().lower()
        record_type = str(record_type or "").strip().lower()

        clauses = ["guild_id = ?"]
        params = [str(guild_id)]
        if query:
            like_query = f"%{query}%"
            clauses.append(
                """
                (
                    LOWER(report_ava) LIKE ?
                    OR LOWER(fined_user_id) LIKE ?
                    OR LOWER(fined_user_name) LIKE ?
                    OR LOWER(reason) LIKE ?
                    OR LOWER(created_by_name) LIKE ?
                    OR LOWER(paid_by_name) LIKE ?
                )
                """
            )
            params.extend([like_query] * 6)
        if status:
            clauses.append("LOWER(status) = ?")
            params.append(status)
        if record_type:
            clauses.append("LOWER(status) = ?")
            params.append(record_type)
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
                    f"SELECT COUNT(*) AS total_items FROM economy_fines WHERE {where_clause}",
                    params,
                ).fetchone()["total_items"] or 0
            )
            meta = page_metadata(page, page_size, total_items)
            offset = (meta["page"] - 1) * meta["page_size"] if meta["total_pages"] else 0
            rows = connection.execute(
                f"""
                SELECT *
                FROM economy_fines
                WHERE {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                params + [meta["page_size"], offset],
            ).fetchall()
        meta["items"] = [dict(row) for row in rows]
        return meta
