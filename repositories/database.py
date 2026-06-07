import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_FILE = os.path.join(DATA_DIR, "bot.sqlite3")


def utc_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
            """
        )
        _ensure_guild_name_column(connection)
        _ensure_albion_registration_columns(connection)
        connection.executescript(
            """

            CREATE INDEX IF NOT EXISTS idx_economy_balances_guild_total
                ON economy_balances (guild_id, items, silver);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_guild_id
                ON economy_operations (guild_id, id);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_player
                ON economy_operations (guild_id, player_id);

            CREATE INDEX IF NOT EXISTS idx_albion_registrations_guild_status
                ON albion_registrations (guild_id, status);

            CREATE INDEX IF NOT EXISTS idx_albion_registrations_player
                ON albion_registrations (player_id);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_guild_status
                ON economy_fines (guild_id, status, id DESC);

            CREATE INDEX IF NOT EXISTS idx_economy_fines_user_status
                ON economy_fines (guild_id, fined_user_id, status);
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
