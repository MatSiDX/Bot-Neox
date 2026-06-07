from repositories.database import get_connection, init_database, utc_now_iso


class AlbionRegistrationRepository:
    def __init__(self):
        init_database()

    def get_config(self, guild_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM albion_registration_config
                WHERE guild_id = ?
                """,
                (str(guild_id),),
            ).fetchone()
        return dict(row) if row else None

    def list_configs(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM albion_registration_config
                WHERE enabled = 1
                ORDER BY guild_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def save_config(
        self,
        guild_id,
        *,
        albion_guild_id,
        albion_guild_name,
        role_id,
        leave_action,
        sync_nickname,
        log_channel_id=None,
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO albion_registration_config (
                    guild_id, albion_guild_id, albion_guild_name, role_id,
                    leave_action, sync_nickname, log_channel_id, enabled,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    albion_guild_id = excluded.albion_guild_id,
                    albion_guild_name = excluded.albion_guild_name,
                    role_id = excluded.role_id,
                    leave_action = excluded.leave_action,
                    sync_nickname = excluded.sync_nickname,
                    log_channel_id = excluded.log_channel_id,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    str(guild_id),
                    str(albion_guild_id),
                    str(albion_guild_name),
                    str(role_id),
                    str(leave_action),
                    int(bool(sync_nickname)),
                    str(log_channel_id) if log_channel_id else None,
                    now,
                    now,
                ),
            )
        return self.get_config(guild_id)

    def disable_config(self, guild_id):
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE albion_registration_config
                SET enabled = 0, updated_at = ?
                WHERE guild_id = ?
                """,
                (utc_now_iso(), str(guild_id)),
            )
        return cursor.rowcount > 0

    def get_registration(self, guild_id, discord_user_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM albion_registrations
                WHERE guild_id = ? AND discord_user_id = ?
                """,
                (str(guild_id), str(discord_user_id)),
            ).fetchone()
        return dict(row) if row else None

    def get_registration_by_player(self, guild_id, player_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM albion_registrations
                WHERE guild_id = ? AND player_id = ?
                """,
                (str(guild_id), str(player_id)),
            ).fetchone()
        return dict(row) if row else None

    def list_registrations(self, guild_id):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM albion_registrations
                WHERE guild_id = ?
                ORDER BY player_name COLLATE NOCASE
                """,
                (str(guild_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_registration(
        self,
        guild_id,
        discord_user_id,
        *,
        discord_user_name,
        player,
        original_nickname=None,
        status="active",
    ):
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO albion_registrations (
                    guild_id, discord_user_id, discord_user_name,
                    player_id, player_name, albion_guild_id, albion_guild_name,
                    alliance_id, alliance_name, original_nickname, status,
                    consecutive_guild_misses, last_checked_at, last_error,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, ?, ?)
                ON CONFLICT(guild_id, discord_user_id) DO UPDATE SET
                    discord_user_name = excluded.discord_user_name,
                    player_id = excluded.player_id,
                    player_name = excluded.player_name,
                    albion_guild_id = excluded.albion_guild_id,
                    albion_guild_name = excluded.albion_guild_name,
                    alliance_id = excluded.alliance_id,
                    alliance_name = excluded.alliance_name,
                    original_nickname = COALESCE(
                        albion_registrations.original_nickname,
                        excluded.original_nickname
                    ),
                    status = excluded.status,
                    consecutive_guild_misses = 0,
                    last_checked_at = excluded.last_checked_at,
                    last_error = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    str(guild_id),
                    str(discord_user_id),
                    str(discord_user_name or ""),
                    str(player.get("Id") or ""),
                    str(player.get("Name") or ""),
                    str(player.get("GuildId") or ""),
                    str(player.get("GuildName") or ""),
                    str(player.get("AllianceId") or ""),
                    str(player.get("AllianceName") or ""),
                    original_nickname,
                    str(status),
                    now,
                    now,
                    now,
                ),
            )
        return self.get_registration(guild_id, discord_user_id)

    def update_from_player(
        self,
        guild_id,
        discord_user_id,
        player,
        *,
        status,
        guild_match=None,
    ):
        now = utc_now_iso()
        if guild_match is True:
            miss_expression = "0"
        elif guild_match is False:
            miss_expression = "consecutive_guild_misses + 1"
        else:
            miss_expression = "consecutive_guild_misses"

        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE albion_registrations
                SET player_name = ?,
                    albion_guild_id = ?,
                    albion_guild_name = ?,
                    alliance_id = ?,
                    alliance_name = ?,
                    status = ?,
                    consecutive_guild_misses = {miss_expression},
                    last_checked_at = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ?
                """,
                (
                    str(player.get("Name") or ""),
                    str(player.get("GuildId") or ""),
                    str(player.get("GuildName") or ""),
                    str(player.get("AllianceId") or ""),
                    str(player.get("AllianceName") or ""),
                    str(status),
                    now,
                    now,
                    str(guild_id),
                    str(discord_user_id),
                ),
            )
        return self.get_registration(guild_id, discord_user_id)

    def set_error(self, guild_id, discord_user_id, error):
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE albion_registrations
                SET last_error = ?, updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ?
                """,
                (
                    str(error)[:500],
                    utc_now_iso(),
                    str(guild_id),
                    str(discord_user_id),
                ),
            )

    def delete_registration(self, guild_id, discord_user_id):
        with get_connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM albion_registrations
                WHERE guild_id = ? AND discord_user_id = ?
                """,
                (str(guild_id), str(discord_user_id)),
            )
        return cursor.rowcount > 0
