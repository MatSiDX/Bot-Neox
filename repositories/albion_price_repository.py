import json

from repositories.database import get_connection, utc_now_iso


class AlbionPriceRepository:
    def get(self, *, server, location, item_unique_name, quality=1):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT server, location, item_unique_name, quality, price, price_type,
                       available, raw_json, fetched_at, updated_at, error
                FROM albion_item_price_cache
                WHERE server = ? AND location = ? AND item_unique_name = ? AND quality = ?
                """,
                (
                    str(server),
                    str(location),
                    str(item_unique_name),
                    int(quality or 1),
                ),
            ).fetchone()
        return self._row_to_dict(row)

    def get_many(self, *, server, location, item_unique_names, quality=1):
        clean_names = [str(name).strip() for name in item_unique_names if str(name or "").strip()]
        if not clean_names:
            return {}

        placeholders = ",".join("?" for _ in clean_names)
        params = [str(server), str(location), int(quality or 1), *clean_names]
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT server, location, item_unique_name, quality, price, price_type,
                       available, raw_json, fetched_at, updated_at, error
                FROM albion_item_price_cache
                WHERE server = ? AND location = ? AND quality = ?
                  AND item_unique_name IN ({placeholders})
                """,
                params,
            ).fetchall()
        return {
            str(row["item_unique_name"]): self._row_to_dict(row)
            for row in rows
        }

    def save(self, *, server, location, item_unique_name, quality, price, price_type, available, raw, error=""):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO albion_item_price_cache (
                    server, location, item_unique_name, quality, price, price_type,
                    available, raw_json, fetched_at, updated_at, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(server, location, item_unique_name, quality) DO UPDATE SET
                    price = excluded.price,
                    price_type = excluded.price_type,
                    available = excluded.available,
                    raw_json = excluded.raw_json,
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at,
                    error = excluded.error
                """,
                (
                    str(server),
                    str(location),
                    str(item_unique_name),
                    int(quality or 1),
                    int(price) if price is not None else None,
                    str(price_type or ""),
                    1 if available else 0,
                    json.dumps(raw or {}, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    str(error or "")[:500],
                ),
            )
        return self.get(
            server=server,
            location=location,
            item_unique_name=item_unique_name,
            quality=quality,
        )

    def invalidate(self, *, server=None, location=None, item_unique_names=None):
        clauses = []
        params = []
        if server:
            clauses.append("server = ?")
            params.append(str(server))
        if location:
            clauses.append("location = ?")
            params.append(str(location))
        if item_unique_names:
            clean_names = [str(name).strip() for name in item_unique_names if str(name or "").strip()]
            if clean_names:
                clauses.append(f"item_unique_name IN ({','.join('?' for _ in clean_names)})")
                params.extend(clean_names)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            cursor = connection.execute(f"DELETE FROM albion_item_price_cache {where}", params)
            return cursor.rowcount

    def _row_to_dict(self, row):
        if not row:
            return None
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except (TypeError, ValueError):
            raw = {}
        return {
            "server": row["server"],
            "location": row["location"],
            "item_unique_name": row["item_unique_name"],
            "quality": int(row["quality"] or 1),
            "price": row["price"],
            "price_type": row["price_type"],
            "available": bool(row["available"]),
            "raw": raw,
            "fetched_at": row["fetched_at"],
            "updated_at": row["updated_at"],
            "error": row["error"],
        }
