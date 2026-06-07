import asyncio

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.albion_api_service import AlbionApiError, AlbionApiService
from services.albion_registration_service import (
    LEAVE_ACTION_KICK,
    LEAVE_ACTION_REMOVE_ROLES,
    STATUS_ACTIVE,
    STATUS_KICKED,
    STATUS_LEFT_GUILD,
    AlbionRegistrationService,
)
from utils.console_logger import log_event


ACCENT_COLOR = discord.Color.from_rgb(0, 184, 255)
SYNC_INTERVAL_HOURS = 6

LEAVE_ACTION_CHOICES = [
    app_commands.Choice(
        name="Quitar el rol y mantenerlo en Discord",
        value=LEAVE_ACTION_REMOVE_ROLES,
    ),
    app_commands.Choice(
        name="Expulsarlo del servidor de Discord",
        value=LEAVE_ACTION_KICK,
    ),
]

STATUS_LABELS = {
    STATUS_ACTIVE: "Activo",
    STATUS_LEFT_GUILD: "Fuera del gremio",
    STATUS_KICKED: "Expulsado",
}


class AlbionRegistrationCog(commands.Cog):
    albion = app_commands.Group(
        name="albion",
        description="Registro de personajes de Albion Online",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot
        self.api = AlbionApiService()
        self.service = AlbionRegistrationService()
        self.sync_lock = asyncio.Lock()

    async def cog_load(self):
        if not self.sync_registrations.is_running():
            self.sync_registrations.start()

    async def cog_unload(self):
        self.sync_registrations.cancel()

    def can_configure(self, member):
        return (
            member.guild_permissions.administrator
            or member.guild_permissions.manage_roles
        )

    def get_bot_member(self, guild):
        return guild.me or guild.get_member(self.bot.user.id)

    def role_is_manageable(self, guild, role):
        bot_member = self.get_bot_member(guild)
        if not bot_member:
            return False
        return role != guild.default_role and role < bot_member.top_role

    def member_is_manageable(self, guild, member):
        bot_member = self.get_bot_member(guild)
        if not bot_member:
            return False
        if member.id == guild.owner_id:
            return False
        return member.top_role < bot_member.top_role

    async def get_member(self, guild, user_id):
        member = guild.get_member(int(user_id))
        if member:
            return member
        try:
            return await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def send_log(self, guild, config, title, description, color):
        log_event(f"ALBION {title} | Servidor: {guild.name} ({guild.id}) | {description}")
        channel_id = config.get("log_channel_id")
        if not channel_id:
            return

        channel = guild.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        embed = discord.Embed(title=title, description=description, color=color)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def apply_active_membership(self, guild, member, registration, config):
        role = guild.get_role(int(config["role_id"]))
        bot_member = self.get_bot_member(guild)
        changes = []
        errors = []

        if not bot_member or not bot_member.guild_permissions.manage_roles:
            errors.append("El bot no tiene el permiso Gestionar roles.")
        elif not role:
            errors.append("El rol configurado ya no existe.")
        elif not self.role_is_manageable(guild, role):
            errors.append("El rol configurado esta por encima del rol del bot.")
        elif role not in member.roles:
            try:
                await member.add_roles(role, reason="Registro de Albion verificado")
                changes.append(f"rol {role.name} asignado")
            except (discord.Forbidden, discord.HTTPException):
                errors.append(f"No pude asignar el rol {role.name}.")

        player_name = str(registration.get("player_name") or "")[:32]
        if (
            config.get("sync_nickname")
            and player_name
            and member.display_name != player_name
        ):
            if not self.member_is_manageable(guild, member):
                errors.append("No puedo modificar el apodo por la jerarquia de roles.")
            else:
                try:
                    await member.edit(
                        nick=player_name,
                        reason="Sincronizacion de nombre de Albion",
                    )
                    changes.append("apodo sincronizado")
                except (discord.Forbidden, discord.HTTPException):
                    errors.append("No pude sincronizar el apodo.")

        return changes, errors

    async def remove_membership_access(self, guild, member, registration, config):
        role = guild.get_role(int(config["role_id"]))
        bot_member = self.get_bot_member(guild)
        changes = []
        errors = []

        if not bot_member or not bot_member.guild_permissions.manage_roles:
            errors.append("El bot no tiene el permiso Gestionar roles.")
        elif role and role in member.roles:
            if not self.role_is_manageable(guild, role):
                errors.append("No puedo quitar el rol configurado por la jerarquia de roles.")
            else:
                try:
                    await member.remove_roles(
                        role,
                        reason="El personaje abandono el gremio de Albion",
                    )
                    changes.append(f"rol {role.name} removido")
                except (discord.Forbidden, discord.HTTPException):
                    errors.append(f"No pude quitar el rol {role.name}.")

        original_nickname = registration.get("original_nickname")
        if config.get("sync_nickname") and member.nick != original_nickname:
            if not self.member_is_manageable(guild, member):
                errors.append("No puedo restaurar el apodo por la jerarquia de roles.")
            else:
                try:
                    await member.edit(
                        nick=original_nickname,
                        reason="El personaje abandono el gremio de Albion",
                    )
                    changes.append("apodo restaurado")
                except (discord.Forbidden, discord.HTTPException):
                    errors.append("No pude restaurar el apodo.")

        return changes, errors

    async def sync_one(self, guild, registration, config, *, announce=True):
        user_id = registration["discord_user_id"]
        try:
            player = await self.api.get_player(registration["player_id"])
        except AlbionApiError as exc:
            self.service.set_error(guild.id, user_id, str(exc))
            return "error"

        if not player or not player.get("Id"):
            self.service.set_error(
                guild.id,
                user_id,
                "La API no devolvio el personaje registrado.",
            )
            return "error"

        belongs_to_guild = (
            str(player.get("GuildId") or "")
            == str(config["albion_guild_id"])
        )
        member = await self.get_member(guild, user_id)

        if belongs_to_guild:
            self.service.update_from_player(
                guild.id,
                user_id,
                player,
                STATUS_ACTIVE,
                guild_match=True,
            )
            if not member:
                return "active_absent"

            refreshed = self.service.get_registration(guild.id, user_id)
            changes, errors = await self.apply_active_membership(
                guild,
                member,
                refreshed,
                config,
            )
            if announce and changes:
                await self.send_log(
                    guild,
                    config,
                    "Registro de Albion actualizado",
                    f"Usuario: {member.mention}\nCambios: {', '.join(changes)}",
                    discord.Color.green(),
                )
            if errors:
                self.service.set_error(guild.id, user_id, " ".join(errors))
            return "active"

        previous_status = registration.get("status")
        checked_registration = self.service.update_from_player(
            guild.id,
            user_id,
            player,
            previous_status,
            guild_match=False,
        )
        if int(checked_registration.get("consecutive_guild_misses", 0)) < 2:
            return "pending"

        self.service.update_from_player(
            guild.id,
            user_id,
            player,
            STATUS_LEFT_GUILD,
        )
        if not member:
            return "left_absent"

        current_guild = player.get("GuildName") or "sin gremio"
        if config["leave_action"] == LEAVE_ACTION_KICK:
            if not self.member_is_manageable(guild, member):
                self.service.set_error(
                    guild.id,
                    user_id,
                    "No puedo expulsar al usuario por la jerarquia de roles.",
                )
                return "error"
            try:
                await member.kick(
                    reason=(
                        f"Abandono el gremio {config['albion_guild_name']} "
                        "en Albion Online"
                    )
                )
            except (discord.Forbidden, discord.HTTPException):
                self.service.set_error(
                    guild.id,
                    user_id,
                    "No pude expulsar al usuario de Discord.",
                )
                return "error"

            self.service.update_from_player(
                guild.id,
                user_id,
                player,
                STATUS_KICKED,
            )
            await self.send_log(
                guild,
                config,
                "Usuario expulsado por salir del gremio",
                (
                    f"Usuario: **{member}** (`{member.id}`)\n"
                    f"Personaje: **{player.get('Name')}**\n"
                    f"Gremio actual: **{current_guild}**"
                ),
                discord.Color.red(),
            )
            return "kicked"

        refreshed = self.service.get_registration(guild.id, user_id)
        changes, errors = await self.remove_membership_access(
            guild,
            member,
            refreshed,
            config,
        )
        if errors:
            self.service.set_error(guild.id, user_id, " ".join(errors))
        if previous_status != STATUS_LEFT_GUILD or changes:
            await self.send_log(
                guild,
                config,
                "Acceso de Albion removido",
                (
                    f"Usuario: {member.mention}\n"
                    f"Personaje: **{player.get('Name')}**\n"
                    f"Gremio actual: **{current_guild}**\n"
                    f"Acciones: {', '.join(changes) if changes else 'sin cambios en Discord'}"
                ),
                discord.Color.orange(),
            )
        return "left"

    async def sync_guild(self, guild, *, announce=True):
        config = self.service.get_config(guild.id)
        if not config:
            return {
                "checked": 0,
                "active": 0,
                "pending": 0,
                "left": 0,
                "kicked": 0,
                "errors": 0,
            }

        summary = {
            "checked": 0,
            "active": 0,
            "pending": 0,
            "left": 0,
            "kicked": 0,
            "errors": 0,
        }
        for registration in self.service.list_registrations(guild.id):
            result = await self.sync_one(
                guild,
                registration,
                config,
                announce=announce,
            )
            summary["checked"] += 1
            if result in ("active", "active_absent"):
                summary["active"] += 1
            elif result in ("left", "left_absent"):
                summary["left"] += 1
            elif result == "pending":
                summary["pending"] += 1
            elif result == "kicked":
                summary["kicked"] += 1
            else:
                summary["errors"] += 1
            await asyncio.sleep(0.25)
        return summary

    @tasks.loop(hours=SYNC_INTERVAL_HOURS)
    async def sync_registrations(self):
        if self.sync_lock.locked():
            return
        async with self.sync_lock:
            for config in self.service.list_configs():
                guild = self.bot.get_guild(int(config["guild_id"]))
                if not guild:
                    continue
                try:
                    await self.sync_guild(guild)
                except Exception as exc:
                    log_event(
                        f"ALBION SYNC ERROR | Servidor: {guild.name} ({guild.id}) | {exc}"
                    )

    @sync_registrations.before_loop
    async def before_sync_registrations(self):
        await self.bot.wait_until_ready()

    @albion.command(
        name="configurar",
        description="Configura el registro para un gremio de Albion de America",
    )
    @app_commands.describe(
        gremio="Nombre exacto del gremio en Albion Online",
        rol="Rol que recibiran los miembros registrados",
        al_salir="Que hacer cuando el personaje abandona el gremio",
        sincronizar_apodo="Cambiar el apodo de Discord al nombre de Albion",
        canal_logs="Canal opcional para avisos de registro y sincronizacion",
    )
    @app_commands.choices(al_salir=LEAVE_ACTION_CHOICES)
    async def configure(
        self,
        interaction: discord.Interaction,
        gremio: str,
        rol: discord.Role,
        al_salir: app_commands.Choice[str],
        sincronizar_apodo: bool = True,
        canal_logs: discord.TextChannel | None = None,
    ):
        if not self.can_configure(interaction.user):
            await interaction.response.send_message(
                "Necesitas el permiso **Gestionar roles** para configurar el registro.",
                ephemeral=True,
            )
            return
        if not self.role_is_manageable(interaction.guild, rol):
            await interaction.response.send_message(
                "El rol elegido debe estar por debajo del rol principal del bot.",
                ephemeral=True,
            )
            return
        bot_member = self.get_bot_member(interaction.guild)
        if not bot_member or not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "El bot necesita el permiso **Gestionar roles**.",
                ephemeral=True,
            )
            return
        if al_salir.value == LEAVE_ACTION_KICK and not bot_member.guild_permissions.kick_members:
            await interaction.response.send_message(
                "El bot necesita el permiso **Expulsar miembros** para usar esa opcion.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            albion_guild = await self.api.find_guild_exact(gremio)
        except AlbionApiError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if not albion_guild:
            await interaction.followup.send(
                "No encontre un gremio con ese nombre exacto en la region **America**.",
                ephemeral=True,
            )
            return

        config = self.service.configure(
            interaction.guild.id,
            albion_guild=albion_guild,
            role_id=rol.id,
            leave_action=al_salir.value,
            sync_nickname=sincronizar_apodo,
            log_channel_id=canal_logs.id if canal_logs else None,
        )
        action_text = (
            "expulsar del servidor"
            if config["leave_action"] == LEAVE_ACTION_KICK
            else "quitar el rol"
        )
        await interaction.followup.send(
            (
                "Configuracion guardada para la region **America**.\n"
                f"Gremio: **{config['albion_guild_name']}**\n"
                f"Rol: {rol.mention}\n"
                f"Al abandonar el gremio: **{action_text}**\n"
                f"Sincronizar apodo: **{'Si' if sincronizar_apodo else 'No'}**\n"
                f"Revision automatica: cada **{SYNC_INTERVAL_HOURS} horas**"
            ),
            ephemeral=True,
        )

    @albion.command(
        name="registrar",
        description="Vincula tu usuario de Discord con tu personaje de Albion",
    )
    @app_commands.describe(nombre="Nombre exacto de tu personaje de Albion")
    async def register(self, interaction: discord.Interaction, nombre: str):
        config = self.service.get_config(interaction.guild.id)
        if not config:
            await interaction.response.send_message(
                "El registro de Albion todavia no esta configurado en este servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            player = await self.api.find_player_exact(nombre)
        except AlbionApiError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if not player:
            await interaction.followup.send(
                "No encontre un personaje con ese nombre exacto en la region **America**.",
                ephemeral=True,
            )
            return

        try:
            registration = self.service.register(
                interaction.guild.id,
                interaction.user,
                player,
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        changes, errors = await self.apply_active_membership(
            interaction.guild,
            interaction.user,
            registration,
            config,
        )
        description = (
            f"Usuario: {interaction.user.mention}\n"
            f"Personaje: **{registration['player_name']}**\n"
            f"Gremio: **{registration['albion_guild_name']}**"
        )
        await self.send_log(
            interaction.guild,
            config,
            "Nuevo registro de Albion",
            description,
            discord.Color.green(),
        )
        response = (
            f"Registro completado como **{registration['player_name']}** "
            f"en **{registration['albion_guild_name']}**."
        )
        if changes:
            response += f"\nCambios: {', '.join(changes)}."
        if errors:
            self.service.set_error(
                interaction.guild.id,
                interaction.user.id,
                " ".join(errors),
            )
            response += f"\nAdvertencias: {' '.join(errors)}"
        response += (
            "\n\nEste registro vincula el personaje encontrado por la API, "
            "pero no constituye una verificacion fuerte de propiedad."
        )
        await interaction.followup.send(response, ephemeral=True)

    @albion.command(
        name="perfil",
        description="Muestra el registro de Albion de un usuario",
    )
    @app_commands.describe(usuario="Usuario que quieres consultar")
    async def profile(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ):
        member = usuario or interaction.user
        registration = self.service.get_registration(
            interaction.guild.id,
            member.id,
        )
        if not registration:
            await interaction.response.send_message(
                f"{member.mention} no tiene un personaje registrado.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Perfil de Albion",
            color=ACCENT_COLOR,
        )
        embed.set_author(
            name=member.display_name,
            icon_url=member.display_avatar.url,
        )
        embed.add_field(
            name="Personaje",
            value=registration["player_name"],
            inline=True,
        )
        embed.add_field(name="Region", value="America", inline=True)
        embed.add_field(
            name="Estado",
            value=STATUS_LABELS.get(registration["status"], registration["status"]),
            inline=True,
        )
        embed.add_field(
            name="Gremio",
            value=registration["albion_guild_name"] or "Sin gremio",
            inline=True,
        )
        embed.add_field(
            name="Alianza",
            value=registration["alliance_name"] or "Sin alianza",
            inline=True,
        )
        embed.add_field(
            name="Ultima revision",
            value=registration["last_checked_at"] or "Pendiente",
            inline=True,
        )
        if registration.get("last_error"):
            embed.add_field(
                name="Ultimo error",
                value=registration["last_error"],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @albion.command(
        name="desvincular",
        description="Elimina tu registro de Albion y el rol asociado",
    )
    async def unregister(self, interaction: discord.Interaction):
        config = self.service.get_config(interaction.guild.id)
        registration = self.service.unregister(
            interaction.guild.id,
            interaction.user.id,
        )
        if not registration:
            await interaction.response.send_message(
                "No tienes un personaje registrado.",
                ephemeral=True,
            )
            return

        errors = []
        if config:
            _, errors = await self.remove_membership_access(
                interaction.guild,
                interaction.user,
                registration,
                config,
            )
        response = "Tu personaje fue desvinculado del bot."
        if errors:
            response += f"\nAdvertencias: {' '.join(errors)}"
        await interaction.response.send_message(response, ephemeral=True)

    @albion.command(
        name="configuracion",
        description="Muestra la configuracion actual del registro de Albion",
    )
    async def configuration(self, interaction: discord.Interaction):
        if not self.can_configure(interaction.user):
            await interaction.response.send_message(
                "Necesitas el permiso **Gestionar roles** para ver esta configuracion.",
                ephemeral=True,
            )
            return

        config = self.service.get_config(interaction.guild.id)
        if not config:
            await interaction.response.send_message(
                "El registro de Albion no esta configurado.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(int(config["role_id"]))
        channel = (
            interaction.guild.get_channel(int(config["log_channel_id"]))
            if config.get("log_channel_id")
            else None
        )
        action = (
            "Expulsar del servidor"
            if config["leave_action"] == LEAVE_ACTION_KICK
            else "Quitar el rol"
        )
        embed = discord.Embed(
            title="Configuracion de registro de Albion",
            color=ACCENT_COLOR,
        )
        embed.add_field(name="Region", value="America", inline=True)
        embed.add_field(
            name="Gremio",
            value=config["albion_guild_name"],
            inline=True,
        )
        embed.add_field(
            name="Rol",
            value=role.mention if role else "Rol eliminado",
            inline=True,
        )
        embed.add_field(name="Al abandonar", value=action, inline=True)
        embed.add_field(
            name="Sincronizar apodo",
            value="Si" if config["sync_nickname"] else "No",
            inline=True,
        )
        embed.add_field(
            name="Canal de logs",
            value=channel.mention if channel else "No configurado",
            inline=True,
        )
        embed.set_footer(
            text=f"Sincronizacion automatica cada {SYNC_INTERVAL_HOURS} horas"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @albion.command(
        name="sincronizar",
        description="Revisa ahora todos los registros del servidor",
    )
    async def synchronize(self, interaction: discord.Interaction):
        if not self.can_configure(interaction.user):
            await interaction.response.send_message(
                "Necesitas el permiso **Gestionar roles** para sincronizar registros.",
                ephemeral=True,
            )
            return
        if not self.service.get_config(interaction.guild.id):
            await interaction.response.send_message(
                "El registro de Albion no esta configurado.",
                ephemeral=True,
            )
            return
        if self.sync_lock.locked():
            await interaction.response.send_message(
                "Ya hay una sincronizacion en curso.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.sync_lock:
            summary = await self.sync_guild(interaction.guild)
        await interaction.followup.send(
            (
                f"Sincronizacion terminada.\n"
                f"Revisados: **{summary['checked']}**\n"
                f"Activos: **{summary['active']}**\n"
                f"Pendientes de segunda confirmacion: **{summary['pending']}**\n"
                f"Fuera del gremio: **{summary['left']}**\n"
                f"Expulsados: **{summary['kicked']}**\n"
                f"Errores: **{summary['errors']}**"
            ),
            ephemeral=True,
        )

    @albion.command(
        name="registrados",
        description="Lista los personajes registrados en este servidor",
    )
    async def registered(self, interaction: discord.Interaction):
        if not self.can_configure(interaction.user):
            await interaction.response.send_message(
                "Necesitas el permiso **Gestionar roles** para ver esta lista.",
                ephemeral=True,
            )
            return

        registrations = self.service.list_registrations(interaction.guild.id)
        if not registrations:
            await interaction.response.send_message(
                "No hay personajes registrados.",
                ephemeral=True,
            )
            return

        lines = []
        for registration in registrations[:40]:
            member = interaction.guild.get_member(
                int(registration["discord_user_id"])
            )
            user_text = (
                member.mention
                if member
                else f"`{registration['discord_user_id']}`"
            )
            status = STATUS_LABELS.get(
                registration["status"],
                registration["status"],
            )
            lines.append(
                f"{user_text} - **{registration['player_name']}** - {status}"
            )

        if len(registrations) > 40:
            lines.append(f"... y {len(registrations) - 40} registros mas.")
        embed = discord.Embed(
            title=f"Registros de Albion ({len(registrations)})",
            description="\n".join(lines),
            color=ACCENT_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AlbionRegistrationCog(bot))
