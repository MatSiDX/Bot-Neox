import argparse
import logging
import os
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATABASE = DEFAULT_DATA_DIR / "bot.sqlite3"
DEFAULT_BACKUP_DIR = Path("/var/backups/bot-neox")
DEFAULT_RETENTION_COUNT = 7
DEFAULT_JSON_FILES = (
    "config.json",
    "permissions.json",
    "ping_templates.json",
    "audit_config.json",
    "ticket_panels.json",
    "active_avalonian_pings.json",
    "report_runtime.json",
    "ticket_records.json",
    "report_dashboard_requests.json",
    "dashboard_sessions.json",
    "audit_events.json",
    "reports.json",
    "avalonian_interactions.json",
    "balances.json",
    "operations.json",
)
SECRET_FILE_NAMES = {".env", ".env.local", ".env.production"}


def env_value(name, default=None):
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip().strip('"').strip("'")
    return value or default


def env_int(name, default):
    value = env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero, valor recibido: {value!r}") from exc


def parse_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def configure_logging(log_file):
    handlers = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def resolve_under_data(data_dir, relative_name):
    if Path(relative_name).is_absolute():
        raise ValueError(f"Los JSON deben configurarse como rutas relativas a data/: {relative_name}")

    path = (data_dir / relative_name).resolve()
    data_root = data_dir.resolve()

    try:
        path.relative_to(data_root)
    except ValueError as exc:
        raise ValueError(f"Ruta fuera de data/ rechazada: {relative_name}") from exc

    if path.name in SECRET_FILE_NAMES or path.name.startswith(".env"):
        raise ValueError(f"Archivo sensible rechazado para backup: {relative_name}")

    if path.suffix.lower() != ".json":
        raise ValueError(f"Solo se aceptan JSON runtime en la lista configurable: {relative_name}")

    return path


def ensure_regular_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"No existe {description}: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"No es un archivo regular {description}: {path}")


def sqlite_backup(source_path, destination_path):
    ensure_regular_file(source_path, "la base SQLite")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Iniciando backup SQLite seguro desde %s", source_path)
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=30)
    try:
        destination = sqlite3.connect(destination_path)
        try:
            source.backup(destination, pages=256, sleep=0.05)
            destination.execute("PRAGMA optimize")
            destination.commit()
        finally:
            destination.close()
    finally:
        source.close()

    verify_sqlite_backup(destination_path)
    logging.info("Backup SQLite consistente creado en staging: %s", destination_path)


def verify_sqlite_backup(database_path):
    connection = sqlite3.connect(database_path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()

    if not result or result[0].lower() != "ok":
        raise RuntimeError(f"PRAGMA integrity_check fallo para {database_path}: {result}")


def copy_json_files(data_dir, json_files, staging_data_dir):
    copied = []
    skipped = []

    for relative_name in json_files:
        source = resolve_under_data(data_dir, relative_name)
        if not source.exists():
            skipped.append(relative_name)
            logging.warning("JSON runtime no existe, se omite: %s", source)
            continue
        if not source.is_file():
            skipped.append(relative_name)
            logging.warning("JSON runtime no es archivo regular, se omite: %s", source)
            continue

        target = staging_data_dir / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative_name)

    return copied, skipped


def copy_sqlite_sidecars(database_path, staging_sidecar_dir):
    copied = []
    for suffix in ("-wal", "-shm"):
        source = Path(f"{database_path}{suffix}")
        if not source.exists():
            continue
        if not source.is_file():
            logging.warning("Sidecar SQLite no es archivo regular, se omite: %s", source)
            continue

        staging_sidecar_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staging_sidecar_dir / source.name)
        copied.append(source.name)
        logging.info("Sidecar SQLite incluido como referencia: %s", source)

    return copied


def write_manifest(staging_dir, timestamp, database_path, json_copied, json_skipped, sidecars):
    manifest = staging_dir / "manifest.txt"
    lines = [
        f"created_at_utc={timestamp}",
        f"project_root={PROJECT_ROOT}",
        f"database_source={database_path}",
        "sqlite_backup=data/bot.sqlite3",
        f"json_copied={','.join(json_copied)}",
        f"json_skipped={','.join(json_skipped)}",
        f"sqlite_sidecars={','.join(sidecars)}",
        "secrets_included=false",
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_archive(staging_dir, backup_dir, timestamp):
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive_path = backup_dir / f"bot-neox-runtime-{timestamp}.tar.gz"
    temp_archive = backup_dir / f".{archive_path.name}.tmp"

    if temp_archive.exists():
        temp_archive.unlink()

    with tarfile.open(temp_archive, "w:gz") as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(staging_dir))

    temp_archive.replace(archive_path)
    logging.info("Backup comprimido creado: %s", archive_path)
    return archive_path


def apply_retention(backup_dir, retention_count):
    if retention_count <= 0:
        logging.info("Retencion desactivada: BOT_NEOX_BACKUP_RETENTION=%s", retention_count)
        return []

    archives = sorted(
        backup_dir.glob("bot-neox-runtime-*.tar.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    expired = archives[retention_count:]

    deleted = []
    for archive in expired:
        archive.unlink()
        deleted.append(archive.name)
        logging.info("Backup antiguo eliminado por retencion: %s", archive)

    return deleted


def run_backup(args):
    data_dir = args.data_dir.resolve()
    database_path = args.database.resolve()
    backup_dir = args.backup_dir.resolve()
    json_files = args.json_files or list(DEFAULT_JSON_FILES)
    timestamp = utc_timestamp()

    if backup_dir == data_dir or data_dir in backup_dir.parents:
        raise ValueError(f"El directorio de backup no puede estar dentro de data/: {backup_dir}")

    ensure_regular_file(database_path, "la base SQLite")
    backup_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = backup_dir / f".bot-neox-backup-{timestamp}.staging"
    if staging_dir.exists():
        raise FileExistsError(f"Ya existe un staging de backup previo: {staging_dir}")

    try:
        staging_dir.mkdir(parents=True)
        staging_data_dir = staging_dir / "data"

        sqlite_backup(database_path, staging_data_dir / "bot.sqlite3")
        sidecars = copy_sqlite_sidecars(database_path, staging_dir / "sqlite-sidecars")
        json_copied, json_skipped = copy_json_files(data_dir, json_files, staging_data_dir)
        write_manifest(staging_dir, timestamp, database_path, json_copied, json_skipped, sidecars)

        archive_path = create_archive(staging_dir, backup_dir, timestamp)
    finally:
        if staging_dir.exists():
            try:
                shutil.rmtree(staging_dir)
            except OSError:
                logging.warning("No se pudo limpiar staging temporal: %s", staging_dir, exc_info=True)

    deleted = apply_retention(backup_dir, args.retention_count)
    logging.info(
        "Backup finalizado: archive=%s json_copied=%s json_skipped=%s retention_deleted=%s",
        archive_path,
        len(json_copied),
        len(json_skipped),
        len(deleted),
    )
    return archive_path


def build_parser():
    env_json_files = parse_csv(env_value("BOT_NEOX_BACKUP_JSON_FILES"))
    parser = argparse.ArgumentParser(description="Backup seguro de runtime Bot-Neox.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(env_value("BOT_NEOX_DATA_DIR", str(DEFAULT_DATA_DIR))),
        help="Directorio runtime data/.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(env_value("BOT_NEOX_BACKUP_DATABASE", str(DEFAULT_DATABASE))),
        help="Ruta de la base SQLite principal.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(env_value("BOT_NEOX_BACKUP_DIR", str(DEFAULT_BACKUP_DIR))),
        help="Directorio externo donde guardar backups.",
    )
    parser.add_argument(
        "--retention-count",
        type=int,
        default=env_int("BOT_NEOX_BACKUP_RETENTION", DEFAULT_RETENTION_COUNT),
        help="Cantidad de backups comprimidos a conservar.",
    )
    parser.add_argument(
        "--json-file",
        dest="json_files",
        action="append",
        default=env_json_files,
        help="JSON critico relativo a data/. Puede repetirse.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(env_value("BOT_NEOX_BACKUP_LOG_FILE", "")) if env_value("BOT_NEOX_BACKUP_LOG_FILE") else None,
        help="Archivo de log adicional. Por defecto solo stdout/journald.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_file)
    try:
        archive_path = run_backup(args)
    except Exception:
        logging.exception("Backup runtime fallido; no se aplico retencion sobre backups previos si no hubo archivo nuevo")
        return 1

    print(archive_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
