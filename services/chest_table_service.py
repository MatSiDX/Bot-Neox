import base64
import os
import re
import secrets
from pathlib import Path

from config.settings import DATA_DIR
from repositories.chest_table_repository import ChestTableRepository


CHEST_IMAGE_DIR = os.path.join(DATA_DIR, "chest_table_images")
CHEST_IMAGE_MAX_BYTES = 5 * 1024 * 1024
CHEST_IMAGE_EXTENSIONS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


class ChestTableService:
    def __init__(self, repository=None):
        self.repository = repository or ChestTableRepository()

    def list_tables(self, guild_id):
        return {"tables": self.repository.list_tables(guild_id)}

    def get_table(self, guild_id, table_id):
        table = self.repository.get_table(guild_id, table_id)
        if not table:
            return None
        return self.with_totals(table)

    def create_table(self, guild_id, name, actor):
        table = self.repository.create_table(guild_id, name, actor)
        return self.with_totals(table)

    def save_table(self, guild_id, table_id, payload, actor):
        normalized = self.normalize_payload(payload)
        table = self.repository.save_table(guild_id, table_id, normalized, actor)
        if not table:
            return None
        return self.with_totals(table)

    def delete_table(self, guild_id, table_id, actor=None):
        return self.repository.delete_table(guild_id, table_id, actor=actor)

    def get_image_file(self, guild_id, image_id):
        image = self.repository.get_image(guild_id, image_id)
        if not image:
            return None
        root = Path(CHEST_IMAGE_DIR).resolve()
        path = (root / image["relative_path"]).resolve()
        if root not in path.parents and path != root:
            return None
        if not path.is_file():
            return None
        return {**image, "path": str(path)}

    def add_image_from_bytes(self, guild_id, table_id, row_id, *, filename, content_type, content, actor, image_type=""):
        if not content:
            raise ValueError("Selecciona una imagen para subir.")
        if len(content) > CHEST_IMAGE_MAX_BYTES:
            raise ValueError("La imagen supera el tamano maximo de 5 MB.")

        extension = self._extension_from_filename(filename)
        if extension not in CHEST_IMAGE_EXTENSIONS:
            raise ValueError("Formato no permitido. Usa png, jpg, jpeg o webp.")

        valid_content = self._content_matches_extension(extension, content)
        if not valid_content:
            raise ValueError("El archivo no parece ser una imagen valida.")

        os.makedirs(CHEST_IMAGE_DIR, exist_ok=True)
        stored_name = f"{guild_id}_{table_id}_{secrets.token_hex(12)}.{extension}"
        stored_path = Path(CHEST_IMAGE_DIR) / stored_name
        with open(stored_path, "xb") as handle:
            handle.write(content)

        actor = actor or {}
        image = self.repository.add_image(
            guild_id,
            table_id,
            row_id,
            {
                "original_name": filename,
                "stored_name": stored_name,
                "relative_path": stored_name,
                "image_type": self._normalize_image_type(image_type),
                "content_type": CHEST_IMAGE_EXTENSIONS[extension],
                "size_bytes": len(content),
                "uploaded_by_id": str(actor.get("id") or ""),
                "uploaded_by_name": str(actor.get("username") or actor.get("global_name") or ""),
            },
        )
        if not image:
            try:
                os.remove(stored_path)
            except OSError:
                pass
            return None
        return image

    def add_image_from_data_url(self, guild_id, table_id, row_id, *, filename, data_url, actor, image_type=""):
        match = re.fullmatch(r"data:([^;,]+);base64,(.+)", str(data_url or ""), flags=re.DOTALL)
        if not match:
            raise ValueError("La imagen adjunta no tiene un formato valido.")
        try:
            content = base64.b64decode(match.group(2), validate=True)
        except ValueError as exc:
            raise ValueError("La imagen adjunta no tiene un formato valido.") from exc
        return self.add_image_from_bytes(
            guild_id,
            table_id,
            row_id,
            filename=filename,
            content_type=match.group(1),
            content=content,
            actor=actor,
            image_type=image_type,
        )

    def normalize_payload(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Datos de tabla invalidos.")
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        cells = payload.get("cells") or {}
        if not isinstance(columns, list) or not columns:
            raise ValueError("La tabla debe tener al menos una columna dinamica.")
        if not isinstance(rows, list):
            raise ValueError("Filas de cofres invalidas.")
        if len(columns) > 40:
            raise ValueError("La tabla no puede tener mas de 40 columnas dinamicas.")
        if len(rows) > 200:
            raise ValueError("La tabla no puede tener mas de 200 cofres.")

        normalized_columns = []
        for position, column in enumerate(columns, start=1):
            if not isinstance(column, dict):
                raise ValueError("Columna invalida.")
            name = re.sub(r"\s+", " ", str(column.get("name") or "")).strip()
            if not name:
                raise ValueError("Todas las columnas deben tener nombre.")
            normalized_columns.append(
                {
                    "id": str(column.get("id") or ""),
                    "name": name[:80],
                    "operation": "-" if str(column.get("operation") or "+").strip() == "-" else "+",
                    "position": position,
                }
            )

        normalized_rows = []
        for position, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError("Fila invalida.")
            default_name = f"Cofre {position}"
            name = re.sub(r"\s+", " ", str(row.get("name") or default_name)).strip()[:80] or default_name
            normalized_rows.append({"id": str(row.get("id") or ""), "name": name, "position": position})

        normalized_cells = {}
        if isinstance(cells, dict):
            for row_id, row_cells in cells.items():
                if not isinstance(row_cells, dict):
                    continue
                clean_row = {}
                for column_id, value in row_cells.items():
                    clean_row[str(column_id)] = self.parse_silver(value)
                normalized_cells[str(row_id)] = clean_row

        return {
            "name": re.sub(r"\s+", " ", str(payload.get("name") or "Tabla de cofres")).strip()[:120] or "Tabla de cofres",
            "columns": normalized_columns,
            "rows": normalized_rows,
            "cells": normalized_cells,
        }

    def parse_silver(self, value):
        if value is None or value == "":
            return 0
        if isinstance(value, bool):
            raise ValueError("Valor numerico invalido.")
        if isinstance(value, int):
            amount = value
        else:
            text = str(value).strip()
            if text.startswith("-"):
                raise ValueError("Los valores de cofres no pueden ser negativos.")
            digits = re.sub(r"\D", "", text)
            amount = int(digits or 0)
        if amount < 0:
            raise ValueError("Los valores de cofres no pueden ser negativos.")
        if amount > 10**15:
            raise ValueError("El valor de una celda es demasiado grande.")
        return amount

    def with_totals(self, table):
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        cells = table.get("cells") or {}
        row_totals = {}
        column_totals = {str(column["id"]): 0 for column in columns}
        grand_total = 0

        for row in rows:
            row_id = str(row["id"])
            row_total = 0
            for column in columns:
                column_id = str(column["id"])
                value = self.parse_silver((cells.get(row_id) or {}).get(column_id, 0))
                column_totals[column_id] += value
                row_total += value if column.get("operation") != "-" else -value
            row_totals[row_id] = row_total
            grand_total += row_total

        return {
            **table,
            "totals": {
                "rows": row_totals,
                "columns": column_totals,
                "grand_total": grand_total,
            },
        }

    def _extension_from_filename(self, filename):
        suffix = Path(str(filename or "")).suffix.lower().lstrip(".")
        return "jpg" if suffix == "jpeg" else suffix

    def _content_matches_extension(self, extension, content):
        if extension == "png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if extension == "jpg":
            return content.startswith(b"\xff\xd8\xff")
        if extension == "webp":
            return content.startswith(b"RIFF") and b"WEBP" in content[:16]
        return False

    def _normalize_image_type(self, image_type):
        normalized = str(image_type or "").strip().lower()
        return normalized if normalized in {"lqs", "lqq"} else ""
