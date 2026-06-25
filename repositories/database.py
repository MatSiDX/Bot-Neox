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
                closed_at TEXT NOT NULL DEFAULT ''
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
            """
        )
        _ensure_guild_name_column(connection)
        _ensure_albion_registration_columns(connection)
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

            CREATE INDEX IF NOT EXISTS idx_economy_fines_guild_created_at
                ON economy_fines (guild_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_user_status
                ON economy_fines (guild_id, fined_user_id, status);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_status
                ON dashboard_action_requests (status, next_retry_at, created_at);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_action_status
                ON dashboard_action_requests (action_type, status, next_retry_at, created_at);

            CREATE INDEX IF NOT EXISTS idx_dashboard_action_requests_guild_created_at
                ON dashboard_action_requests (guild_id, created_at DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_action_requests_idempotency
                ON dashboard_action_requests (idempotency_key)
                WHERE idempotency_key IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_guild_config_guild_id
                ON guild_config (guild_id, key);

            CREATE INDEX IF NOT EXISTS idx_role_permissions_guild_role
                ON role_permissions (guild_id, role_id);

            CREATE INDEX IF NOT EXISTS idx_role_permissions_guild_permission
                ON role_permissions (guild_id, permission);
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
