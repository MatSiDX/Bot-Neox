import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config.settings import DATA_DIR, DATABASE_FILE
import os


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS economy_balances (
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                user_id TEXT NOT NULL,
                user_name TEXT,
                items INTEGER NOT NULL DEFAULT 0,
                silver INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS economy_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                action TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                operator_id TEXT NOT NULL DEFAULT '',
                player TEXT NOT NULL DEFAULT '',
                player_id TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL DEFAULT 0,
                previous_balance,
                new_balance,
                reason TEXT NOT NULL DEFAULT '',
                player_status TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL DEFAULT '',
                time TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS albion_registration_config (
                guild_id TEXT PRIMARY KEY,
                albion_guild_id TEXT NOT NULL,
                albion_guild_name TEXT NOT NULL,
                role_id TEXT NOT NULL,
                leave_action TEXT NOT NULL DEFAULT 'remove_roles',
                sync_nickname INTEGER NOT NULL DEFAULT 1,
                log_channel_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS albion_registrations (
                guild_id TEXT NOT NULL,
                discord_user_id TEXT NOT NULL,
                discord_user_name TEXT,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                albion_guild_id TEXT,
                albion_guild_name TEXT,
                alliance_id TEXT,
                alliance_name TEXT,
                original_nickname TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                consecutive_guild_misses INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, discord_user_id),
                UNIQUE (guild_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS economy_fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                report_ava TEXT NOT NULL DEFAULT '',
                fined_user_id TEXT NOT NULL,
                fined_user_name TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                proof_path TEXT NOT NULL DEFAULT '',
                proof_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                blocked_role_id TEXT NOT NULL DEFAULT '',
                resolver_role_id TEXT NOT NULL DEFAULT '',
                ticket_channel_id TEXT NOT NULL DEFAULT '',
                ticket_message_id TEXT NOT NULL DEFAULT '',
                announcement_channel_id TEXT NOT NULL DEFAULT '',
                announcement_message_id TEXT NOT NULL DEFAULT '',
                created_by_id TEXT NOT NULL DEFAULT '',
                created_by_name TEXT NOT NULL DEFAULT '',
                paid_by_id TEXT NOT NULL DEFAULT '',
                paid_by_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                paid_at TEXT NOT NULL DEFAULT '',
                closed_at TEXT NOT NULL DEFAULT '',
                deleted_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS dashboard_action_requests (
                id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                requested_by TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                processed_at TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at TEXT NOT NULL DEFAULT '',
                locked_by TEXT NOT NULL DEFAULT '',
                locked_at TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT,
                correlation_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS bot_message_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id TEXT NOT NULL DEFAULT '',
                operator_name TEXT NOT NULL DEFAULT '',
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                action TEXT NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                previous_content TEXT NOT NULL DEFAULT '',
                new_content TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                error TEXT NOT NULL DEFAULT '',
                request_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS server_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                guild_name TEXT NOT NULL DEFAULT '',
                created_by_id TEXT NOT NULL DEFAULT '',
                created_by_name TEXT NOT NULL DEFAULT '',
                schema_version INTEGER NOT NULL DEFAULT 1,
                backup_json TEXT NOT NULL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS server_template_restores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL DEFAULT '',
                backup_id INTEGER NOT NULL,
                source_guild_id TEXT NOT NULL,
                source_guild_name TEXT NOT NULL DEFAULT '',
                target_guild_id TEXT NOT NULL,
                target_guild_name TEXT NOT NULL DEFAULT '',
                operator_id TEXT NOT NULL DEFAULT '',
                operator_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                options_json TEXT NOT NULL DEFAULT '{}',
                preview_json TEXT NOT NULL DEFAULT '{}',
                id_map_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, key)
            );

            CREATE TABLE IF NOT EXISTS role_permissions (
                guild_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id, permission)
            );

            CREATE TABLE IF NOT EXISTS active_avalonian_pings (
                guild_id TEXT NOT NULL,
                caller_id TEXT NOT NULL,
                numero_ava TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                active INTEGER NOT NULL DEFAULT 1,
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deactivated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (guild_id, caller_id, numero_ava)
            );

            CREATE TABLE IF NOT EXISTS albion_item_price_cache (
                server TEXT NOT NULL,
                location TEXT NOT NULL,
                item_unique_name TEXT NOT NULL,
                quality INTEGER NOT NULL DEFAULT 1,
                price INTEGER,
                price_type TEXT NOT NULL DEFAULT '',
                available INTEGER NOT NULL DEFAULT 0,
                raw_json TEXT NOT NULL DEFAULT '{}',
                fetched_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (server, location, item_unique_name, quality)
            );

            CREATE TABLE IF NOT EXISTS chest_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'Tabla de cofres',
                created_by_id TEXT NOT NULL DEFAULT '',
                created_by_name TEXT NOT NULL DEFAULT '',
                updated_by_id TEXT NOT NULL DEFAULT '',
                updated_by_name TEXT NOT NULL DEFAULT '',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS chest_table_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                operation TEXT NOT NULL DEFAULT '+',
                position INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (table_id) REFERENCES chest_tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chest_table_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (table_id) REFERENCES chest_tables(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chest_table_cells (
                table_id INTEGER NOT NULL,
                row_id INTEGER NOT NULL,
                column_id INTEGER NOT NULL,
                value INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (row_id, column_id),
                FOREIGN KEY (table_id) REFERENCES chest_tables(id) ON DELETE CASCADE,
                FOREIGN KEY (row_id) REFERENCES chest_table_rows(id) ON DELETE CASCADE,
                FOREIGN KEY (column_id) REFERENCES chest_table_columns(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chest_table_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                row_id INTEGER,
                guild_id TEXT NOT NULL,
                original_name TEXT NOT NULL DEFAULT '',
                stored_name TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                image_type TEXT NOT NULL DEFAULT '',
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                uploaded_by_id TEXT NOT NULL DEFAULT '',
                uploaded_by_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (table_id) REFERENCES chest_tables(id) ON DELETE CASCADE,
                FOREIGN KEY (row_id) REFERENCES chest_table_rows(id) ON DELETE SET NULL
            );

            """
        )
        _ensure_guild_name_column(connection)
        _ensure_economy_operation_detail_columns(connection)
        _ensure_albion_registration_columns(connection)
        _ensure_economy_fines_soft_delete_columns(connection)
        _ensure_chest_table_image_columns(connection)
        connection.executescript(
            """

            CREATE INDEX IF NOT EXISTS idx_economy_balances_guild_total
                ON economy_balances (guild_id, items, silver);

            CREATE INDEX IF NOT EXISTS idx_economy_balances_guild_user_name
                ON economy_balances (guild_id, user_name COLLATE NOCASE);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_guild_id
                ON economy_operations (guild_id, id);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_guild_created_at
                ON economy_operations (guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_player
                ON economy_operations (guild_id, player_id);

            CREATE INDEX IF NOT EXISTS idx_albion_registrations_guild_status
                ON albion_registrations (guild_id, status);

            CREATE INDEX IF NOT EXISTS idx_albion_registrations_guild_player_name
                ON albion_registrations (guild_id, player_name COLLATE NOCASE);

            CREATE INDEX IF NOT EXISTS idx_albion_registrations_player
                ON albion_registrations (player_id);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_guild_status
                ON economy_fines (guild_id, status, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_guild_deleted
                ON economy_fines (guild_id, is_deleted, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_guild_created_at
                ON economy_fines (guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_user_status
                ON economy_fines (guild_id, fined_user_id, status);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_ticket_channel
                ON economy_fines (guild_id, ticket_channel_id);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_status
                ON dashboard_action_requests (status, next_retry_at, created_at);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_action_status
                ON dashboard_action_requests (action_type, status, next_retry_at, created_at);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_guild_created_at
                ON dashboard_action_requests (guild_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_bot_message_audit_guild_created_at
                ON bot_message_audit (guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_bot_message_audit_request
                ON bot_message_audit (request_id);

            CREATE INDEX IF NOT EXISTS idx_server_backups_guild_created_at
                ON server_backups (guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_server_template_restores_target_created_at
                ON server_template_restores (target_guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_server_template_restores_request
                ON server_template_restores (request_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_action_requests_idempotency
                ON dashboard_action_requests (idempotency_key)
                WHERE idempotency_key IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_guild_config_guild_id
                ON guild_config (guild_id, key);

            CREATE INDEX IF NOT EXISTS idx_role_permissions_guild_role
                ON role_permissions (guild_id, role_id);

            CREATE INDEX IF NOT EXISTS idx_role_permissions_guild_permission
                ON role_permissions (guild_id, permission);

            CREATE INDEX IF NOT EXISTS idx_active_avalonian_pings_active
                ON active_avalonian_pings (active, guild_id, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_active_avalonian_pings_guild_status
                ON active_avalonian_pings (guild_id, status, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_albion_item_price_cache_item
                ON albion_item_price_cache (item_unique_name, server, location, quality);

            CREATE INDEX IF NOT EXISTS idx_albion_item_price_cache_updated_at
                ON albion_item_price_cache (updated_at);

            CREATE INDEX IF NOT EXISTS idx_chest_tables_guild
                ON chest_tables (guild_id, is_deleted, updated_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_chest_columns_table_position
                ON chest_table_columns (table_id, is_deleted, position, id);

            CREATE INDEX IF NOT EXISTS idx_chest_rows_table_position
                ON chest_table_rows (table_id, is_deleted, position, id);

            CREATE INDEX IF NOT EXISTS idx_chest_cells_table
                ON chest_table_cells (table_id, row_id, column_id);

            CREATE INDEX IF NOT EXISTS idx_chest_images_table
                ON chest_table_images (table_id, row_id, id DESC);

            """
        )


def _table_columns(connection, table_name):
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _ensure_guild_name_column(connection):
    if "guild_name" not in _table_columns(connection, "economy_balances"):
        connection.executescript(
            """
            ALTER TABLE economy_balances RENAME TO economy_balances_old;

            CREATE TABLE economy_balances (
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                user_id TEXT NOT NULL,
                user_name TEXT,
                items INTEGER NOT NULL DEFAULT 0,
                silver INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            INSERT INTO economy_balances (
                guild_id, guild_name, user_id, user_name, items, silver, created_at, updated_at
            )
            SELECT guild_id, NULL, user_id, user_name, items, silver, created_at, updated_at
            FROM economy_balances_old;

            DROP TABLE economy_balances_old;
            """
        )

    if "guild_name" not in _table_columns(connection, "economy_operations"):
        connection.executescript(
            """
            ALTER TABLE economy_operations RENAME TO economy_operations_old;

            CREATE TABLE economy_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                guild_name TEXT,
                action TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                operator_id TEXT NOT NULL DEFAULT '',
                player TEXT NOT NULL DEFAULT '',
                player_id TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL DEFAULT 0,
                previous_balance,
                new_balance,
                date TEXT NOT NULL DEFAULT '',
                time TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            INSERT INTO economy_operations (
                id, guild_id, guild_name, action, operator, operator_id, player, player_id,
                type, category, amount, previous_balance, new_balance, date, time, created_at
            )
            SELECT
                id, guild_id, NULL, action, operator, operator_id, player, player_id,
                type, category, amount, previous_balance, new_balance, date, time, created_at
            FROM economy_operations_old;

            DROP TABLE economy_operations_old;
            """
        )


def _ensure_albion_registration_columns(connection):
    columns = _table_columns(connection, "albion_registrations")
    if "consecutive_guild_misses" not in columns:
        connection.execute(
            """
            ALTER TABLE albion_registrations
            ADD COLUMN consecutive_guild_misses INTEGER NOT NULL DEFAULT 0
            """
        )


def _ensure_economy_operation_detail_columns(connection):
    columns = _table_columns(connection, "economy_operations")
    if "reason" not in columns:
        connection.execute(
            """
            ALTER TABLE economy_operations
            ADD COLUMN reason TEXT NOT NULL DEFAULT ''
            """
        )
    if "player_status" not in columns:
        connection.execute(
            """
            ALTER TABLE economy_operations
            ADD COLUMN player_status TEXT NOT NULL DEFAULT ''
            """
        )


def _ensure_economy_fines_soft_delete_columns(connection):
    columns = _table_columns(connection, "economy_fines")
    if "is_deleted" not in columns:
        connection.execute(
            """
            ALTER TABLE economy_fines
            ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0
            """
        )
    if "deleted_at" not in columns:
        connection.execute(
            """
            ALTER TABLE economy_fines
            ADD COLUMN deleted_at TEXT NOT NULL DEFAULT ''
            """
        )


def _ensure_chest_table_image_columns(connection):
    columns = _table_columns(connection, "chest_table_images")
    if "image_type" not in columns:
        connection.execute(
            """
            ALTER TABLE chest_table_images
            ADD COLUMN image_type TEXT NOT NULL DEFAULT ''
            """
        )
