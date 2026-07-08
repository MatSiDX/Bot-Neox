from repositories.database import get_connection, utc_now_iso


class ChestTableRepository:
    def list_tables(self, guild_id):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, guild_id, name, created_by_id, created_by_name,
                       updated_by_id, updated_by_name, created_at, updated_at
                FROM chest_tables
                WHERE guild_id = ? AND is_deleted = 0
                ORDER BY updated_at DESC, id DESC
                """,
                (str(guild_id),),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_table(self, guild_id, table_id):
        with get_connection() as connection:
            table = self._get_table_row(connection, guild_id, table_id)
            if not table:
                return None
            return self._hydrate_table(connection, table)

    def get_image(self, guild_id, image_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT image.*
                FROM chest_table_images image
                JOIN chest_tables table_record ON table_record.id = image.table_id
                WHERE image.id = ? AND image.guild_id = ? AND table_record.is_deleted = 0
                """,
                (int(image_id), str(guild_id)),
            ).fetchone()
            return dict(row) if row else None

    def create_table(self, guild_id, name, actor):
        now = utc_now_iso()
        actor_id = str((actor or {}).get("id") or "")
        actor_name = str((actor or {}).get("username") or (actor or {}).get("global_name") or "")
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chest_tables (
                    guild_id, name, created_by_id, created_by_name,
                    updated_by_id, updated_by_name, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(name or "Tabla de cofres")[:120], actor_id, actor_name, actor_id, actor_name, now, now),
            )
            table_id = cursor.lastrowid
            for position, column in enumerate((("LQS", "+"), ("LQQ", "+")), start=1):
                connection.execute(
                    """
                    INSERT INTO chest_table_columns (table_id, name, operation, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (table_id, column[0], column[1], position, now, now),
                )
            table = self._hydrate_table(connection, self._get_table_row(connection, guild_id, table_id))
            return table

    def save_table(self, guild_id, table_id, payload, actor):
        now = utc_now_iso()
        actor_id = str((actor or {}).get("id") or "")
        actor_name = str((actor or {}).get("username") or (actor or {}).get("global_name") or "")
        with get_connection() as connection:
            table = self._get_table_row(connection, guild_id, table_id)
            if not table:
                return None

            name = str(payload.get("name") or table["name"] or "Tabla de cofres").strip()[:120] or "Tabla de cofres"
            connection.execute(
                """
                UPDATE chest_tables
                SET name = ?, updated_by_id = ?, updated_by_name = ?, updated_at = ?
                WHERE id = ? AND guild_id = ? AND is_deleted = 0
                """,
                (name, actor_id, actor_name, now, int(table_id), str(guild_id)),
            )

            column_id_map = self._replace_columns(connection, int(table_id), payload.get("columns") or [], now)
            row_id_map = self._replace_rows(connection, int(table_id), payload.get("rows") or [], now)
            self._replace_cells(connection, int(table_id), payload.get("cells") or {}, column_id_map, row_id_map, now)
            return self._hydrate_table(connection, self._get_table_row(connection, guild_id, table_id))

    def delete_table(self, guild_id, table_id, actor=None):
        now = utc_now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE chest_tables
                SET is_deleted = 1, deleted_at = ?, updated_at = ?
                WHERE id = ? AND guild_id = ? AND is_deleted = 0
                """,
                (now, now, int(table_id), str(guild_id)),
            )
            return cursor.rowcount > 0

    def add_image(self, guild_id, table_id, row_id, image):
        now = utc_now_iso()
        with get_connection() as connection:
            table = self._get_table_row(connection, guild_id, table_id)
            if not table:
                return None
            normalized_row_id = int(row_id) if str(row_id or "").isdigit() else None
            if normalized_row_id:
                row = connection.execute(
                    """
                    SELECT id FROM chest_table_rows
                    WHERE id = ? AND table_id = ? AND is_deleted = 0
                    """,
                    (normalized_row_id, int(table_id)),
                ).fetchone()
                if not row:
                    normalized_row_id = None

            cursor = connection.execute(
                """
                INSERT INTO chest_table_images (
                    table_id, row_id, guild_id, original_name, stored_name, relative_path,
                    image_type, content_type, size_bytes, uploaded_by_id, uploaded_by_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(table_id),
                    normalized_row_id,
                    str(guild_id),
                    str(image.get("original_name") or "")[:180],
                    str(image.get("stored_name") or ""),
                    str(image.get("relative_path") or ""),
                    str(image.get("image_type") or "")[:40],
                    str(image.get("content_type") or ""),
                    int(image.get("size_bytes") or 0),
                    str(image.get("uploaded_by_id") or ""),
                    str(image.get("uploaded_by_name") or ""),
                    now,
                ),
            )
            connection.execute(
                "UPDATE chest_tables SET updated_at = ? WHERE id = ?",
                (now, int(table_id)),
            )
            return self._get_image_by_id(connection, cursor.lastrowid)

    def _replace_columns(self, connection, table_id, columns, now):
        existing = {
            int(row["id"]): dict(row)
            for row in connection.execute(
                "SELECT * FROM chest_table_columns WHERE table_id = ?",
                (table_id,),
            ).fetchall()
        }
        kept = set()
        id_map = {}
        for position, column in enumerate(columns, start=1):
            name = str(column.get("name") or "").strip()[:80]
            if not name:
                raise ValueError("Todas las columnas deben tener nombre.")
            operation = "-" if str(column.get("operation") or "+").strip() == "-" else "+"
            raw_id = column.get("id")
            column_id = int(raw_id) if str(raw_id or "").isdigit() and int(raw_id) in existing else None
            if column_id:
                connection.execute(
                    """
                    UPDATE chest_table_columns
                    SET name = ?, operation = ?, position = ?, is_deleted = 0, deleted_at = '', updated_at = ?
                    WHERE id = ? AND table_id = ?
                    """,
                    (name, operation, position, now, column_id, table_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO chest_table_columns (table_id, name, operation, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (table_id, name, operation, position, now, now),
                )
                column_id = cursor.lastrowid
            kept.add(column_id)
            id_map[str(raw_id or column_id)] = column_id
            id_map[str(column_id)] = column_id

        for column_id in set(existing) - kept:
            connection.execute(
                """
                UPDATE chest_table_columns
                SET is_deleted = 1, deleted_at = ?, updated_at = ?
                WHERE id = ? AND table_id = ?
                """,
                (now, now, column_id, table_id),
            )
        return id_map

    def _replace_rows(self, connection, table_id, rows, now):
        existing = {
            int(row["id"]): dict(row)
            for row in connection.execute(
                "SELECT * FROM chest_table_rows WHERE table_id = ?",
                (table_id,),
            ).fetchall()
        }
        kept = set()
        id_map = {}
        for position, row in enumerate(rows, start=1):
            name = str(row.get("name") or f"Cofre {position}").strip()[:80] or f"Cofre {position}"
            raw_id = row.get("id")
            row_id = int(raw_id) if str(raw_id or "").isdigit() and int(raw_id) in existing else None
            if row_id:
                connection.execute(
                    """
                    UPDATE chest_table_rows
                    SET name = ?, position = ?, is_deleted = 0, deleted_at = '', updated_at = ?
                    WHERE id = ? AND table_id = ?
                    """,
                    (name, position, now, row_id, table_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO chest_table_rows (table_id, name, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (table_id, name, position, now, now),
                )
                row_id = cursor.lastrowid
            kept.add(row_id)
            id_map[str(raw_id or row_id)] = row_id
            id_map[str(row_id)] = row_id

        for row_id in set(existing) - kept:
            connection.execute(
                """
                UPDATE chest_table_rows
                SET is_deleted = 1, deleted_at = ?, updated_at = ?
                WHERE id = ? AND table_id = ?
                """,
                (now, now, row_id, table_id),
            )
        return id_map

    def _replace_cells(self, connection, table_id, cells, column_id_map, row_id_map, now):
        connection.execute(
            """
            DELETE FROM chest_table_cells
            WHERE table_id = ?
            """,
            (table_id,),
        )
        if not isinstance(cells, dict):
            return
        for raw_row_id, row_cells in cells.items():
            row_id = row_id_map.get(str(raw_row_id))
            if not row_id or not isinstance(row_cells, dict):
                continue
            for raw_column_id, raw_value in row_cells.items():
                column_id = column_id_map.get(str(raw_column_id))
                if not column_id:
                    continue
                value = int(raw_value or 0)
                if value < 0:
                    raise ValueError("Los valores de cofres no pueden ser negativos.")
                connection.execute(
                    """
                    INSERT INTO chest_table_cells (table_id, row_id, column_id, value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (table_id, row_id, column_id, value, now, now),
                )

    def _get_table_row(self, connection, guild_id, table_id):
        row = connection.execute(
            """
            SELECT * FROM chest_tables
            WHERE id = ? AND guild_id = ? AND is_deleted = 0
            """,
            (int(table_id), str(guild_id)),
        ).fetchone()
        return dict(row) if row else None

    def _hydrate_table(self, connection, table):
        table_id = int(table["id"])
        columns = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, name, operation, position
                FROM chest_table_columns
                WHERE table_id = ? AND is_deleted = 0
                ORDER BY position, id
                """,
                (table_id,),
            ).fetchall()
        ]
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, name, position
                FROM chest_table_rows
                WHERE table_id = ? AND is_deleted = 0
                ORDER BY position, id
                """,
                (table_id,),
            ).fetchall()
        ]
        cells = {}
        for row in connection.execute(
            """
            SELECT row_id, column_id, value
            FROM chest_table_cells
            WHERE table_id = ?
            """,
            (table_id,),
        ).fetchall():
            cells.setdefault(str(row["row_id"]), {})[str(row["column_id"])] = int(row["value"] or 0)

        images = [
            self._image_payload(dict(row))
            for row in connection.execute(
                """
                SELECT * FROM chest_table_images
                WHERE table_id = ?
                ORDER BY id DESC
                """,
                (table_id,),
            ).fetchall()
        ]
        return {**table, "columns": columns, "rows": rows, "cells": cells, "images": images}

    def _get_image_by_id(self, connection, image_id):
        row = connection.execute(
            "SELECT * FROM chest_table_images WHERE id = ?",
            (int(image_id),),
        ).fetchone()
        return self._image_payload(dict(row)) if row else None

    def _image_payload(self, row):
        return {
            "id": row["id"],
            "table_id": row["table_id"],
            "row_id": row["row_id"],
            "guild_id": row["guild_id"],
            "image_type": row["image_type"] if "image_type" in row else "",
            "original_name": row["original_name"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "created_at": row["created_at"],
            "url": f"/chest-table-image/{row['id']}",
        }
