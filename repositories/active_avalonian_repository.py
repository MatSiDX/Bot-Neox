import os
import json

from repositories.balance_repository import DATA_DIR
from repositories.database import get_connection, init_database, utc_now_iso
from utils.json_store import read_json

ACTIVE_AVALONIAN_FILE = os.path.join(DATA_DIR, "active_avalonian_pings.json")


class ActiveAvalonianRepository:
    def __init__(self):
        init_database()
        self.migrate_legacy_json()

    def load(self):
        data = {}
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM active_avalonian_pings
                ORDER BY guild_id, caller_id, numero_ava
                """
            ).fetchall()

        for row in rows:
            state = self.decode_state(row["state_json"])
            guild_id = str(state.get("guild_id") or "")
            caller_id = str(state.get("caller_id") or "")
            numero_ava = str(state.get("numero_ava") or "")
            if not all([guild_id, caller_id, numero_ava]):
                continue
            data.setdefault(guild_id, {}).setdefault(caller_id, {})[numero_ava] = state
        return data

    def save(self, data):
        for guild_states in (data or {}).values():
            for caller_states in guild_states.values():
                for state in caller_states.values():
                    self.upsert(state)

    def upsert(self, state):
        guild_id = str(state["guild_id"])
        caller_id = str(state["caller_id"])
        numero_ava = str(state["numero_ava"])
        stored_state = dict(state)
        stored_state["active"] = not (
            stored_state.get("cancelled")
            or (
                stored_state.get("finalized")
                and (
                    stored_state.get("report_sent")
                    or (
                        stored_state.get("report_generated")
                        and not stored_state.get("report_rejected")
                    )
                )
            )
        )
        stored_state["status"] = self.resolve_status(stored_state)
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO active_avalonian_pings (
                    guild_id, caller_id, numero_ava, status, active, state_json,
                    created_at, updated_at, deactivated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, caller_id, numero_ava) DO UPDATE SET
                    status = excluded.status,
                    active = excluded.active,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at,
                    deactivated_at = excluded.deactivated_at
                """,
                (
                    guild_id,
                    caller_id,
                    numero_ava,
                    stored_state["status"],
                    1 if stored_state["active"] else 0,
                    self.encode_state(stored_state),
                    now,
                    now,
                    now if not stored_state["active"] else "",
                ),
            )

    def resolve_status(self, state):
        if state.get("cancelled"):
            return "cancelled"
        if state.get("finalized"):
            return "finalized"
        return "active"

    def deactivate(self, guild_id, caller_id, numero_ava, status):
        gid = str(guild_id)
        cid = str(caller_id)
        ava = str(numero_ava)
        now = utc_now_iso()
        normalized_status = str(status or "inactive")
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM active_avalonian_pings
                WHERE guild_id = ? AND caller_id = ? AND numero_ava = ?
                """,
                (gid, cid, ava),
            ).fetchone()
            if row is None:
                return False

            state = self.decode_state(row["state_json"])
            state["active"] = False
            state["status"] = normalized_status
            state["deactivated_at"] = now
            connection.execute(
                """
                UPDATE active_avalonian_pings
                SET status = ?,
                    active = 0,
                    state_json = ?,
                    updated_at = ?,
                    deactivated_at = ?
                WHERE guild_id = ? AND caller_id = ? AND numero_ava = ?
                """,
                (normalized_status, self.encode_state(state), now, now, gid, cid, ava),
            )
        return True

    def remove(self, guild_id, caller_id, numero_ava):
        with get_connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM active_avalonian_pings
                WHERE guild_id = ? AND caller_id = ? AND numero_ava = ?
                """,
                (str(guild_id), str(caller_id), str(numero_ava)),
            )
        return cursor.rowcount > 0

    def get_all_states(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT state_json
                FROM active_avalonian_pings
                WHERE active = 1
                ORDER BY updated_at ASC
                """
            ).fetchall()
        return [self.decode_state(row["state_json"]) for row in rows]

    def migrate_legacy_json(self):
        if not os.path.isfile(ACTIVE_AVALONIAN_FILE):
            return

        data = read_json(ACTIVE_AVALONIAN_FILE, {})
        if not data:
            return

        with get_connection() as connection:
            existing_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM active_avalonian_pings"
                ).fetchone()["count"]
                or 0
            )
        if existing_count:
            return

        for guild_states in data.values():
            for caller_states in guild_states.values():
                for state in caller_states.values():
                    self.upsert(state)

    def encode_state(self, state):
        return json.dumps(state, ensure_ascii=False, sort_keys=True)

    def decode_state(self, value):
        try:
            state = json.loads(value or "{}")
        except (TypeError, ValueError):
            return {}
        return state if isinstance(state, dict) else {}
