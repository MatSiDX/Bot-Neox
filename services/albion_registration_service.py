from repositories.albion_registration_repository import AlbionRegistrationRepository


LEAVE_ACTION_REMOVE_ROLES = "remove_roles"
LEAVE_ACTION_KICK = "kick"
VALID_LEAVE_ACTIONS = {LEAVE_ACTION_REMOVE_ROLES, LEAVE_ACTION_KICK}

STATUS_ACTIVE = "active"
STATUS_LEFT_GUILD = "left_guild"
STATUS_KICKED = "kicked"


class AlbionRegistrationService:
    def __init__(self, repo=None):
        self.repo = repo or AlbionRegistrationRepository()

    def get_config(self, guild_id):
        config = self.repo.get_config(guild_id)
        if not config or not int(config.get("enabled", 0)):
            return None
        config["sync_nickname"] = bool(config.get("sync_nickname"))
        return config

    def list_configs(self):
        configs = self.repo.list_configs()
        for config in configs:
            config["sync_nickname"] = bool(config.get("sync_nickname"))
        return configs

    def configure(
        self,
        guild_id,
        *,
        albion_guild,
        role_id,
        leave_action,
        sync_nickname,
        log_channel_id=None,
    ):
        if leave_action not in VALID_LEAVE_ACTIONS:
            raise ValueError("Accion de salida no valida.")
        return self.repo.save_config(
            guild_id,
            albion_guild_id=albion_guild["Id"],
            albion_guild_name=albion_guild["Name"],
            role_id=role_id,
            leave_action=leave_action,
            sync_nickname=sync_nickname,
            log_channel_id=log_channel_id,
        )

    def disable(self, guild_id):
        return self.repo.disable_config(guild_id)

    def get_registration(self, guild_id, discord_user_id):
        return self.repo.get_registration(guild_id, discord_user_id)

    def list_registrations(self, guild_id):
        return self.repo.list_registrations(guild_id)

    def validate_player_for_registration(self, guild_id, discord_user_id, player):
        config = self.get_config(guild_id)
        if not config:
            return False, "El registro de Albion no esta configurado en este servidor."

        if str(player.get("GuildId") or "") != str(config["albion_guild_id"]):
            current_guild = player.get("GuildName") or "sin gremio"
            return (
                False,
                f"El personaje pertenece a **{current_guild}**, no a **{config['albion_guild_name']}**.",
            )

        claimed = self.repo.get_registration_by_player(guild_id, player.get("Id"))
        if claimed and str(claimed["discord_user_id"]) != str(discord_user_id):
            return False, "Ese personaje ya esta vinculado a otra cuenta de Discord."

        return True, None

    def register(self, guild_id, member, player):
        valid, error = self.validate_player_for_registration(guild_id, member.id, player)
        if not valid:
            raise ValueError(error)

        existing = self.get_registration(guild_id, member.id)
        original_nickname = (
            existing.get("original_nickname")
            if existing
            else member.nick
        )
        return self.repo.save_registration(
            guild_id,
            member.id,
            discord_user_name=str(member),
            player=player,
            original_nickname=original_nickname,
            status=STATUS_ACTIVE,
        )

    def update_from_player(
        self,
        guild_id,
        discord_user_id,
        player,
        status,
        *,
        guild_match=None,
    ):
        return self.repo.update_from_player(
            guild_id,
            discord_user_id,
            player,
            status=status,
            guild_match=guild_match,
        )

    def set_error(self, guild_id, discord_user_id, error):
        self.repo.set_error(guild_id, discord_user_id, error)

    def unregister(self, guild_id, discord_user_id):
        registration = self.get_registration(guild_id, discord_user_id)
        if not registration:
            return None
        self.repo.delete_registration(guild_id, discord_user_id)
        return registration
