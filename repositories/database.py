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
            """
        )
        _ensure_guild_name_column(connection)
        connection.executescript(
            """

            CREATE INDEX IF NOT EXISTS idx_economy_balances_guild_total
                ON economy_balances (guild_id, items, silver);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_guild_id
                ON economy_operations (guild_id, id);

            CREATE INDEX IF NOT EXISTS idx_economy_operations_player
                ON economy_operations (guild_id, player_id);
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
