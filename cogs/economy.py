import asyncio
import re
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

from config.settings import AVALONIAN_LOG_CHANNEL_ID
from services.avalonian_service import AvalonianService
from services.active_avalonian_service import ActiveAvalonianService
from services.balance_service import BalanceService
from services.config_service import CONFIG_REPORT_APPROVED_CHANNEL, CONFIG_REPORT_REVIEW_CHANNEL, ConfigService
from services.ping_template_service import MAX_TEMPLATES_PER_GUILD, PingTemplateService
from services.permission_service import (
    PERMISSION_ECONOMY,
    PERMISSION_GLOBAL,
    PERMISSION_PERMISSIONS,
    PERMISSION_PING,
    PERMISSION_REPORTS,
    PERMISSION_TEMPLATES,
    PermissionService,
)
from services.report_service import ReportService
from utils.formatters import format_number
from views.avalonian_ping_view import AvalonSignupView
from views.top_view import TopView

ACCENT_COLOR = discord.Color.from_rgb(0, 184, 255)

CATEGORY_CHOICES = [
    app_commands.Choice(name="Items", value="items"),
    app_commands.Choice(name="Silver", value="silver"),
]

PERMISSION_CHOICES = [
    app_commands.Choice(name="Balance", value=PERMISSION_ECONOMY),
    app_commands.Choice(name="Ping", value=PERMISSION_PING),
    app_commands.Choice(name="Plantillas", value=PERMISSION_TEMPLATES),
    app_commands.Choice(name="Informes", value=PERMISSION_REPORTS),
    app_commands.Choice(name="Permisos", value=PERMISSION_PERMISSIONS),
    app_commands.Choice(name="Global", value=PERMISSION_GLOBAL),
]

PERMISSION_LABELS = {
    PERMISSION_ECONOMY: "Balance",
    PERMISSION_PING: "Ping",
    PERMISSION_TEMPLATES: "Plantillas",
    PERMISSION_REPORTS: "Informes",
    PERMISSION_PERMISSIONS: "Permisos",
    PERMISSION_GLOBAL: "Global",
}

CONFIG_CHANNEL_CHOICES = [
    app_commands.Choice(name="Evaluacion Informes", value=CONFIG_REPORT_REVIEW_CHANNEL),
    app_commands.Choice(name="Informes Aprobados", value=CONFIG_REPORT_APPROVED_CHANNEL),
]


class PingTemplateModal(discord.ui.Modal):
    def __init__(self, cog, template, *, fill_for_testing=False):
        modal_title = f"Ping: {template.get('name', 'Plantilla')}"[:45]
        super().__init__(title=modal_title)
        self.cog = cog
        self.template = template
        self.fill_for_testing = fill_for_testing

        self.numero = discord.ui.TextInput(
            label="1. Numero del ping",
            placeholder="Ej: 29",
            max_length=20,
        )
        self.content = discord.ui.TextInput(
            label="2. Mensaje completo",
            style=discord.TextStyle.paragraph,
            default=str(template.get("content", ""))[:4000],
            placeholder="# Ava {numero}\n\n/join {caller}\n\nMainTank:\nHeal:\nDPS:\n\nCupos: {occupied}/{total}{status}",
            max_length=4000,
        )
        self.roles = discord.ui.TextInput(
            label="3. Botones/roles",
            style=discord.TextStyle.paragraph,
            default="\n".join(template.get("roles", []))[:1500],
            placeholder="El primer rol queda reservado para el caller.\nMainTank\nHeal\nDPS\nScout",
            max_length=1500,
        )

        self.add_item(self.numero)
        self.add_item(self.content)
        self.add_item(self.roles)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.publish_ping_from_modal(
            interaction,
            self.template,
            numero_text=str(self.numero.value),
            roles_text=str(self.roles.value),
            content=str(self.content.value),
            fill_for_testing=self.fill_for_testing,
        )


class PingTemplateCreateModal(discord.ui.Modal):
    def __init__(self, cog, template_key, template_name):
        super().__init__(title="Agregar plantilla")
        self.cog = cog
        self.template_key = template_key
        self.template_name = template_name

        self.content = discord.ui.TextInput(
            label="1. Mensaje completo",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            placeholder="# Ava {numero}\n\n/join {caller}\n\nMainTank:\nHeal:\nDPS:\n\nCupos: {occupied}/{total}{status}",
        )
        self.roles = discord.ui.TextInput(
            label="2. Botones/roles",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            placeholder="El primer rol queda reservado para el caller.\nMainTank\nHeal\nDPS\nScout",
        )

        self.add_item(self.content)
        self.add_item(self.roles)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_ping_template_from_modal(
            interaction,
            template_key=self.template_key,
            template_name=self.template_name,
            roles_text=str(self.roles.value),
            content=str(self.content.value),
        )


class EconomyCog(commands.Cog):
    config_group = app_commands.Group(name="config", description="Configuracion del bot")
    template_group = app_commands.Group(name="plantilla", description="Gestion de plantillas de ping")

    def __init__(self, bot):
        self.bot = bot
        self.service = BalanceService()
        self.avalonian_service = AvalonianService()
        self.active_avalonian_service = ActiveAvalonianService()
        self.config_service = ConfigService()
        self.ping_template_service = PingTemplateService()
        self.permission_service = PermissionService()
        self.report_service = ReportService()
        self.active_avalonian_views = {}
        self.restore_task = None
        self.restored_active_views = False

    def has_economy_permission(self, interaction):
        return self.permission_service.can_manage_balance(interaction.guild.id, interaction.user)

    def has_ping_permission(self, interaction):
        return self.permission_service.can_manage_ping(interaction.guild.id, interaction.user)

    def has_template_permission(self, interaction):
        return self.permission_service.can_manage_templates(interaction.guild.id, interaction.user)

    def can_manage_permissions(self, interaction):
        return (
            interaction.user.guild_permissions.administrator
            or self.permission_service.can_manage_permissions(interaction.guild.id, interaction.user)
        )

    def clean_player_name(self, display_name):
        name = re.sub(r"\[[^\]]*\]", "", display_name)
        name = re.sub(r"\([^)]*\)", "", name)
        name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
        return " ".join(name.split())

    def format_template_text(self, text, **values):
        class SafeValues(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        return str(text or "").format_map(SafeValues(values))

    def build_join_command(self, template, caller_name, numero_ava, title=None):
        return self.format_template_text(
            template.get("join_command", "/join {caller}"),
            caller=caller_name,
            numero=numero_ava,
            title=title or template.get("title", ""),
            template=template.get("name", ""),
        )

    def resolve_message_title_fallback(self, template, numero_ava):
        title_template = str(template.get("title") or "Ping {numero}")
        return self.format_template_text(
            title_template,
            numero=numero_ava,
            template=template.get("name", ""),
        ).strip() or f"Ping {numero_ava}"

    def derive_ping_title_from_message(self, content, fallback):
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            line = re.sub(r"<@!?\d+>|<@&\d+>|<#\d+>", "", line)
            line = re.sub(r"@everyone|@here", "", line, flags=re.IGNORECASE)
            line = re.sub(r"https?://\S+", "", line)
            line = re.sub(r"^[#>\-\s*`_~]+", "", line)
            line = re.sub(r"[*_`~|]", "", line)
            line = " ".join(line.split())
            if line:
                return line[:100]

        return str(fallback or "Ping")[:100]

    def parse_ping_number(self, value):
        match = re.search(r"\d+", str(value or ""))
        if not match:
            return None

        return int(match.group(0))

    def parse_template_roles(self, value):
        roles = []
        for raw_role in re.split(r"[\n,;]+", str(value or "")):
            role_name = re.sub(r"^\s*\d+[\.\)]\s*", "", raw_role).strip()
            if not role_name:
                continue

            roles.append(role_name)

        return roles

    async def publish_ping_from_modal(
        self,
        interaction,
        template,
        *,
        numero_text,
        roles_text,
        content,
        fill_for_testing=False,
    ):
        numero_ava = self.parse_ping_number(numero_text)
        if numero_ava is None:
            await interaction.response.send_message(
                "Debes indicar un numero valido para el ping.",
                ephemeral=True,
            )
            return

        key = self.get_avalonian_key(interaction, interaction.user.id, numero_ava)
        if key in self.active_avalonian_views and not self.active_avalonian_views[key].finalized and not self.active_avalonian_views[key].cancelled:
            active_view = self.active_avalonian_views[key]
            await interaction.response.send_message(
                f"Ya tienes un ping activo para {active_view.title}. Usa otro numero o administra ese ping.",
                ephemeral=True,
            )
            return

        roles = self.parse_template_roles(roles_text)
        if len(roles) < 2:
            await interaction.response.send_message(
                "La plantilla necesita al menos dos roles: el rol del caller y un cupo disponible.",
                ephemeral=True,
            )
            return

        if len(roles) > 21:
            await interaction.response.send_message(
                "La plantilla puede tener como maximo 21 roles para que todos entren como botones.",
                ephemeral=True,
            )
            return

        if not str(content or "").strip():
            await interaction.response.send_message(
                "Debes indicar el mensaje del ping.",
                ephemeral=True,
            )
            return

        edited_template = dict(template)
        edited_template["join_command"] = template.get("join_command") or "/join {caller}"
        fallback_title = self.resolve_message_title_fallback(edited_template, numero_ava)
        caller_name = self.clean_player_name(interaction.user.display_name) or interaction.user.name
        preview_content = self.format_template_text(
            content,
            title=fallback_title,
            numero=numero_ava,
            template=edited_template.get("name", ""),
            mention=edited_template.get("mention", ""),
            join_command=self.build_join_command(edited_template, caller_name, numero_ava, fallback_title),
            caller=caller_name,
            slots="",
            loot_link=edited_template.get("loot_link", ""),
            occupied=1,
            total=len(roles),
            status="",
        )
        title = self.derive_ping_title_from_message(preview_content, fallback_title)

        edited_template["title"] = title
        edited_template["roles"] = roles
        edited_template["caller_slot"] = roles[0]
        edited_template["content"] = content

        resolved_join_command = self.build_join_command(edited_template, caller_name, numero_ava, title)
        view = AvalonSignupView(
            numero_ava=numero_ava,
            join_command=resolved_join_command,
            caller=interaction.user,
            caller_name=caller_name,
            template=edited_template,
            template_key=edited_template.get("key", template.get("key", "avalonianas")),
            title=title,
            guild_id=interaction.guild.id,
            log_channel_id=AVALONIAN_LOG_CHANNEL_ID,
            avalonian_service=self.avalonian_service,
            config_service=self.config_service,
            report_service=self.report_service,
            permission_service=self.permission_service,
            balance_service=self.service,
            persist_callback=self.persist_active_view_state,
            remove_persisted_callback=self.remove_active_view_state,
        )

        if fill_for_testing:
            candidate_ids = []
            seen_ids = {interaction.user.id}
            for member in interaction.guild.members:
                if member.id in seen_ids:
                    continue
                candidate_ids.append(member.id)
                seen_ids.add(member.id)
                if len(candidate_ids) >= len(view.slot_names) - 1:
                    break

            while len(candidate_ids) < len(view.slot_names) - 1:
                candidate_ids.append(interaction.user.id)

            view.fill_for_testing(candidate_ids)

        await interaction.response.send_message(
            content=view.build_content(),
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        view.attach_message(await interaction.original_response())
        self.active_avalonian_views[key] = view
        await self.create_avalonian_thread(interaction, view.message, view.title)

    async def create_ping_template_from_modal(
        self,
        interaction,
        *,
        template_key,
        template_name,
        roles_text,
        content,
    ):
        roles = self.parse_template_roles(roles_text)
        if len(roles) < 2:
            await interaction.response.send_message(
                "La plantilla necesita al menos dos roles: el rol del caller y un cupo disponible.",
                ephemeral=True,
            )
            return

        if len(roles) > 21:
            await interaction.response.send_message(
                "La plantilla puede tener como maximo 21 roles para que todos entren como botones.",
                ephemeral=True,
            )
            return

        if not str(content or "").strip():
            await interaction.response.send_message(
                "Debes indicar el mensaje de la plantilla.",
                ephemeral=True,
            )
            return

        template, error = self.ping_template_service.add_template(
            interaction.guild.id,
            template_key,
            {
                "name": template_name or template_key,
                "title": "",
                "title_editable": True,
                "mention": "",
                "join_command": "/join {caller}",
                "caller_slot": roles[0],
                "roles": roles,
                "slot_format": "",
                "content": content,
                "loot_link": "",
                "report_enabled": True,
            },
        )
        if error == "invalid":
            await interaction.response.send_message(
                "La clave de la plantilla no es valida. Usa letras, numeros, guion o guion bajo.",
                ephemeral=True,
            )
            return

        if error == "exists":
            await interaction.response.send_message(
                f"Ya existe una plantilla con la clave `{template_key}`.",
                ephemeral=True,
            )
            return

        if error == "limit":
            await interaction.response.send_message(
                "Este servidor ya tiene 5 plantillas guardadas. Elimina una antes de crear otra.",
                ephemeral=True,
            )
            return

        if error == "reserved":
            await interaction.response.send_message(
                "Esa clave esta reservada para la plantilla temporal desde cero.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Plantilla **{template['name']}** guardada como `{template['key']}`.",
            ephemeral=True,
        )

    def build_balance_embed(self, guild, member, items, silver, total):
        ranking = self.service.get_ranking(guild)
        member_rank = next((index for index, (user_id, _) in enumerate(ranking, start=1) if user_id == member.id), None)

        embed = discord.Embed(
            title="Balance",
            description=f"**💼 Balance de {member.mention}**",
            color=ACCENT_COLOR,
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📦 Items", value=format_number(items), inline=True)
        embed.add_field(name="💰 Silver", value=format_number(silver), inline=True)
        embed.add_field(name="🏦 Total", value=format_number(total), inline=True)

        if member_rank is not None:
            embed.set_footer(text=f"Leaderboard Rank: {member_rank}")
        else:
            embed.set_footer(text="Leaderboard Rank: Sin posicion")

        return embed

    def get_stored_user_name(self, guild_id, user_id):
        data = self.service.repo.load()
        user = data.get(str(guild_id), {}).get(str(user_id), {})
        return user.get("name")

    def get_avalonian_key(self, interaction, user_id, numero_ava):
        return (interaction.guild.id, user_id, numero_ava)

    def get_active_avalonian_view(self, interaction, numero_ava):
        view = self.active_avalonian_views.get(
            self.get_avalonian_key(interaction, interaction.user.id, numero_ava)
        )
        if view and (view.finalized or view.cancelled):
            return None
        return view

    def is_matching_avalonian_view(self, view, numero_ava):
        return view is not None and view.numero_ava == numero_ava and not view.finalized and not view.cancelled

    def get_accessible_avalonian_views(self, interaction):
        views = []
        for (guild_id, caller_id, numero_ava), view in self.active_avalonian_views.items():
            if guild_id == interaction.guild.id and caller_id == interaction.user.id and not view.finalized and not view.cancelled:
                views.append((numero_ava, view))
        return sorted(views, key=lambda item: item[0])

    def persist_active_view_state(self, state):
        self.active_avalonian_service.save_state(state)

    def remove_active_view_state(self, guild_id, caller_id, numero_ava):
        self.active_avalonian_service.remove_state(guild_id, caller_id, numero_ava)

    async def cog_load(self):
        if self.restore_task is None:
            self.restore_task = self.bot.loop.create_task(self.restore_active_avalonian_views())

    def cog_unload(self):
        if self.restore_task and not self.restore_task.done():
            self.restore_task.cancel()

    async def restore_active_avalonian_views(self):
        await self.bot.wait_until_ready()
        if self.restored_active_views:
            return

        self.restored_active_views = True
        for guild in self.bot.guilds:
            self.service.register_guild(guild)

        for state in self.active_avalonian_service.get_all_states():
            guild_id = int(state.get("guild_id", 0))
            caller_id = int(state.get("caller_id", 0))
            numero_ava = int(state.get("numero_ava", 0))
            channel_id = int(state.get("channel_id", 0))
            message_id = int(state.get("message_id", 0))

            if not all([guild_id, caller_id, numero_ava, channel_id, message_id]):
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    self.remove_active_view_state(guild_id, caller_id, numero_ava)
                    continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.HTTPException:
                self.remove_active_view_state(guild_id, caller_id, numero_ava)
                continue

            view = AvalonSignupView.from_state(
                state,
                avalonian_service=self.avalonian_service,
                config_service=self.config_service,
                report_service=self.report_service,
                permission_service=self.permission_service,
                balance_service=self.service,
                persist_callback=self.persist_active_view_state,
                remove_persisted_callback=self.remove_active_view_state,
            )
            view.message = message
            self.bot.add_view(view, message_id=message_id)
            self.active_avalonian_views[(guild_id, caller_id, numero_ava)] = view

            if view.cancelled and (view.delete_task is None or view.delete_task.done()):
                view.delete_task = asyncio.create_task(view.delete_cancelled_message_later())

    async def avalonian_number_autocomplete(self, interaction, current):
        choices = []
        current_text = str(current or "")
        for numero_ava, view in self.get_accessible_avalonian_views(interaction):
            if current_text and current_text not in str(numero_ava):
                continue

            taken = sum(1 for user_id in view.slots.values() if user_id)
            choices.append(
                app_commands.Choice(
                    name=f"{view.title} - {taken}/{len(view.slots)} cupos",
                    value=numero_ava,
                )
            )

        return choices[:25]

    async def ping_template_autocomplete(self, interaction, current):
        choices = []
        current_text = str(current or "").lower()
        for template_key, template in self.ping_template_service.get_templates(
            interaction.guild.id,
            include_scratch=True,
        ).items():
            template_name = template.get("name", template_key)
            if current_text and current_text not in template_key.lower() and current_text not in template_name.lower():
                continue

            choices.append(
                app_commands.Choice(
                    name=template_name,
                    value=template_key,
                )
            )

        return choices[:25]

    async def saved_ping_template_autocomplete(self, interaction, current):
        choices = []
        current_text = str(current or "").lower()
        for template_key, template in self.ping_template_service.get_saved_templates(interaction.guild.id).items():
            template_name = template.get("name", template_key)
            if current_text and current_text not in template_key.lower() and current_text not in template_name.lower():
                continue

            choices.append(
                app_commands.Choice(
                    name=template_name,
                    value=template_key,
                )
            )

        return choices[:25]

    async def avalonian_slot_autocomplete(self, interaction, current):
        numero_ava = getattr(getattr(interaction, "namespace", None), "numero_ava", None)
        view = self.get_active_avalonian_view(interaction, numero_ava) if numero_ava else None
        if not view:
            return []

        current_text = str(current or "").lower()
        choices = []
        for slot_name in view.available_slot_labels():
            if current_text and current_text not in slot_name.lower():
                continue

            choices.append(app_commands.Choice(name=slot_name, value=slot_name))

        return choices[:25]

    async def create_avalonian_thread(self, interaction, message, title):
        try:
            return await message.create_thread(name=str(title)[:100])
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(
                "El ping fue publicado, pero no pude crear el hilo. Revisa que el bot tenga permisos para crear hilos en este canal.",
                ephemeral=True,
            )
            return None

    def build_top_embed(self, guild, chunk, page_index, total_pages, viewer_rank):
        embed = discord.Embed(
            title="🏛️ Leaderboard",
            description=f"**Ranking de {guild.name}**",
            color=ACCENT_COLOR,
        )

        lines = []
        for position, user_id, total in chunk:
            member = guild.get_member(user_id)
            display_name = member.display_name if member else self.get_stored_user_name(guild.id, user_id)
            display_name = display_name or f"Usuario {user_id}"
            lines.append(f"**{position}.** {display_name} - 🪙 {format_number(total)}")

        embed.add_field(
            name="Top Jugadores",
            value="\n\n".join(lines),
            inline=False,
        )
        embed.set_footer(text=f"Pagina {page_index}/{total_pages} • Tu posicion: {viewer_rank}")
        return embed

    async def modify_balance(self, interaction, member, amount, key, add, command_name):
        previous_items, previous_silver = self.service.get_balance(interaction.guild, member.id)
        previous_balance = previous_items if key == "items" else previous_silver

        self.service.modify(interaction.guild, member.id, amount, key, add)

        current_items, current_silver = self.service.get_balance(interaction.guild, member.id)
        new_balance = current_items if key == "items" else current_silver

        now = datetime.now()
        self.service.log_operation(
            interaction.guild,
            {
                "action": command_name,
                "operator": interaction.user.display_name,
                "operator_id": str(interaction.user.id),
                "player": member.display_name,
                "player_id": str(member.id),
                "type": "ADD" if add else "REMOVE",
                "category": "Items" if key == "items" else "Silver",
                "amount": amount,
                "previous_balance": previous_balance,
                "new_balance": new_balance,
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M"),
            },
        )

        icon = "✅" if add else "❌"
        action = "Añadido" if add else "Removido"
        resource_name = "Items" if key == "items" else "Silver"
        await interaction.response.send_message(
            f"{icon} {action} 💰 {format_number(amount)} al saldo de {member.mention}. [{resource_name}]"
        )

    @app_commands.command(name="balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        items, silver = self.service.get_balance(interaction.guild, member.id)
        total = items + silver
        embed = self.build_balance_embed(interaction.guild, member, items, silver, total)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="top")
    async def top(self, interaction: discord.Interaction):
        ranking = self.service.get_ranking(interaction.guild)
        if not ranking:
            await interaction.response.send_message("No hay datos en este servidor.")
            return

        viewer_rank = next(
            (index for index, (user_id, _) in enumerate(ranking, start=1) if user_id == interaction.user.id),
            "Sin posicion",
        )

        embeds = []
        total_pages = (len(ranking) + 9) // 10

        for page_number, start_index in enumerate(range(0, len(ranking), 10), start=1):
            raw_chunk = ranking[start_index:start_index + 10]
            chunk = [
                (position, user_id, total)
                for position, (user_id, total) in enumerate(raw_chunk, start=start_index + 1)
            ]
            embeds.append(
                self.build_top_embed(
                    interaction.guild,
                    chunk,
                    page_number,
                    total_pages,
                    viewer_rank,
                )
            )

        view = TopView(embeds, owner_id=interaction.user.id)
        await interaction.response.send_message(embed=embeds[0], view=view)

    @app_commands.command(name="ping")
    @app_commands.describe(
        plantilla="Plantilla que quieres publicar",
    )
    @app_commands.autocomplete(plantilla=ping_template_autocomplete)
    async def ping(
        self,
        interaction: discord.Interaction,
        plantilla: str,
    ):
        if not self.has_ping_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True,
            )
            return

        template = self.ping_template_service.get_template(interaction.guild.id, plantilla)
        await interaction.response.send_modal(PingTemplateModal(self, template))

    @app_commands.command(name="ping-test")
    @app_commands.describe(
        plantilla="Plantilla que quieres probar",
    )
    @app_commands.autocomplete(plantilla=ping_template_autocomplete)
    async def ping_test(
        self,
        interaction: discord.Interaction,
        plantilla: str,
    ):
        if not self.has_ping_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True,
            )
            return

        template = self.ping_template_service.get_template(interaction.guild.id, plantilla)
        await interaction.response.send_modal(PingTemplateModal(self, template, fill_for_testing=True))

    @template_group.command(name="agregar")
    @app_commands.describe(
        clave="Nombre interno corto, por ejemplo avalonianas o zvz-roja",
        nombre="Nombre visible de la plantilla",
    )
    async def add_ping_template(self, interaction: discord.Interaction, clave: str, nombre: str = None):
        if not self.has_template_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para gestionar plantillas.",
                ephemeral=True,
            )
            return

        normalized_key = self.ping_template_service.normalize_key(clave)
        if not normalized_key:
            await interaction.response.send_message(
                "La clave de la plantilla no es valida. Usa letras, numeros, guion o guion bajo.",
                ephemeral=True,
            )
            return

        if not self.ping_template_service.can_add_template(interaction.guild.id):
            await interaction.response.send_message(
                "Este servidor ya tiene 5 plantillas guardadas. Elimina una antes de crear otra.",
                ephemeral=True,
            )
            return

        if normalized_key in self.ping_template_service.get_templates(interaction.guild.id):
            await interaction.response.send_message(
                f"Ya existe una plantilla con la clave `{normalized_key}`. Eliminala antes de crearla de nuevo.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            PingTemplateCreateModal(
                self,
                normalized_key,
                nombre or normalized_key,
            )
        )

    @template_group.command(name="eliminar")
    @app_commands.describe(plantilla="Plantilla que quieres eliminar")
    @app_commands.autocomplete(plantilla=saved_ping_template_autocomplete)
    async def delete_ping_template(self, interaction: discord.Interaction, plantilla: str):
        if not self.has_template_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para gestionar plantillas.",
                ephemeral=True,
            )
            return

        removed = self.ping_template_service.delete_template(interaction.guild.id, plantilla)
        if not removed:
            await interaction.response.send_message(
                "No pude eliminar esa plantilla. La plantilla base no se puede eliminar.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Plantilla `{plantilla}` eliminada.",
            ephemeral=True,
        )

    @template_group.command(name="listar")
    async def list_ping_templates(self, interaction: discord.Interaction):
        if not self.has_template_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para ver plantillas.",
                ephemeral=True,
            )
            return

        saved_templates = self.ping_template_service.get_saved_templates(interaction.guild.id)
        all_templates = self.ping_template_service.get_templates(interaction.guild.id, include_scratch=True)
        saved_count = self.ping_template_service.get_template_count(interaction.guild.id)

        lines = []
        for template_key, template in all_templates.items():
            if template_key == "desde-cero":
                source = "temporal"
            elif template_key in saved_templates:
                source = "servidor"
            else:
                source = "base"
            lines.append(f"`{template_key}` - {template.get('name', template_key)} ({source})")

        embed = discord.Embed(
            title="Plantillas de ping",
            description="\n".join(lines) if lines else "No hay plantillas disponibles.",
            color=ACCENT_COLOR,
        )
        embed.set_footer(text=f"Guardadas en este servidor: {saved_count}/{MAX_TEMPLATES_PER_GUILD}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @template_group.command(name="ayuda")
    async def ping_template_help(self, interaction: discord.Interaction):
        if not self.has_template_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para ver ayuda de plantillas.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Ayuda de plantillas",
            color=ACCENT_COLOR,
        )
        embed.add_field(
            name="Flujo rapido",
            value=(
                "Usa `/ping desde-cero` para crear un ping sin guardarlo.\n"
                "Usa `/plantilla agregar` para guardar una plantilla del servidor."
            ),
            inline=False,
        )
        embed.add_field(
            name="Botones/roles",
            value=(
                "Escribe un boton por linea. El primero queda reservado para el caller.\n"
                "Ejemplo:\n"
                "```text\nMainTank\nHeal\nDPS\nScout\n```"
            ),
            inline=False,
        )
        embed.add_field(
            name="Mensaje completo",
            value=(
                "Escribe el mensaje tal cual quieres publicarlo. Si una linea contiene el nombre de un boton, el bot agregara ahi la mencion del jugador.\n"
                "Ejemplo:\n"
                "```text\n# Ava {numero}\n\n/join {caller}\n\nMainTank:\nHeal:\nDPS:\n\n{occupied}/{total}{status}\n```"
            ),
            inline=False,
        )
        embed.add_field(
            name="Placeholders",
            value="`{title}` `{numero}` `{caller}` `{join_command}` `{slots}` `{occupied}` `{total}` `{status}` `{loot_link}`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping-list")
    async def ping_list(self, interaction: discord.Interaction):
        pings = self.get_accessible_avalonian_views(interaction)
        if not pings:
            await interaction.response.send_message(
                "No tienes pings activos para administrar en este servidor.",
                ephemeral=True,
            )
            return

        lines = []
        for numero_ava, view in pings:
            taken = sum(1 for user_id in view.slots.values() if user_id)
            message_link = view.message.jump_url if view.message else "Sin enlace"
            lines.append(f"**{view.title}** - Cupos ocupados: {taken}/{len(view.slots)} - [Ver ping]({message_link})")

        embed = discord.Embed(
            title="Pings que puedes administrar",
            description="\n".join(lines),
            color=ACCENT_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping-add")
    @app_commands.describe(
        numero_ava="Numero de Ava que se va a modificar",
        member="Usuario que sera anotado",
        rol="Rol/cupo donde sera anotado",
    )
    @app_commands.autocomplete(numero_ava=avalonian_number_autocomplete)
    @app_commands.autocomplete(rol=avalonian_slot_autocomplete)
    async def ping_add(
        self,
        interaction: discord.Interaction,
        numero_ava: int,
        member: discord.Member,
        rol: str,
    ):
        view = self.get_active_avalonian_view(interaction, numero_ava)
        if not self.is_matching_avalonian_view(view, numero_ava):
            await interaction.response.send_message(
                f"No tienes un ping activo para administrar Ava {numero_ava} en este servidor.",
                ephemeral=True,
            )
            return

        success, message = view.assign_user(rol, member)
        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await view.refresh_message()
        await interaction.response.send_message(f"✅ {message}", ephemeral=True)

    @app_commands.command(name="ping-remove")
    @app_commands.describe(
        numero_ava="Numero de Ava que se va a modificar",
        member="Usuario que sera removido del ping",
    )
    @app_commands.autocomplete(numero_ava=avalonian_number_autocomplete)
    async def ping_remove(self, interaction: discord.Interaction, numero_ava: int, member: discord.Member):
        view = self.get_active_avalonian_view(interaction, numero_ava)
        if not self.is_matching_avalonian_view(view, numero_ava):
            await interaction.response.send_message(
                f"No tienes un ping activo para administrar Ava {numero_ava} en este servidor.",
                ephemeral=True,
            )
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "Usted para poder desanotarse del Ava tiene que dejar un encargado u otro caller para que pueda realizarlo. Usa /ping-transfer numero_ava member.",
                ephemeral=True,
            )
            return

        slot_name, message = view.remove_user_by_admin(member)
        if not slot_name:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await view.refresh_message()
        await interaction.response.send_message(f"✅ {message}", ephemeral=True)

    @app_commands.command(name="ping-transfer")
    @app_commands.describe(
        numero_ava="Numero de Ava que se va a transferir",
        member="Nuevo caller que quedara a cargo del ping",
    )
    @app_commands.autocomplete(numero_ava=avalonian_number_autocomplete)
    async def ping_transfer(self, interaction: discord.Interaction, numero_ava: int, member: discord.Member):
        view = self.get_active_avalonian_view(interaction, numero_ava)
        if not self.is_matching_avalonian_view(view, numero_ava):
            await interaction.response.send_message(
                f"No tienes un ping activo para administrar Ava {numero_ava} en este servidor.",
                ephemeral=True,
            )
            return

        new_key = self.get_avalonian_key(interaction, member.id, numero_ava)
        if new_key in self.active_avalonian_views:
            await interaction.response.send_message(
                f"{member.mention} ya administra un ping activo para Ava {numero_ava}.",
                ephemeral=True,
            )
            return

        caller_name = self.clean_player_name(member.display_name) or member.name
        join_command = view.format_template_text(
            view.template.get("join_command", "/join {caller}"),
            caller=caller_name,
            numero=numero_ava,
            title=view.title,
            template=view.template.get("name", ""),
        )
        success, released_slot = view.transfer_caller(member, join_command)
        if not success:
            await interaction.response.send_message(released_slot, ephemeral=True)
            return

        old_key = self.get_avalonian_key(interaction, interaction.user.id, numero_ava)
        self.remove_active_view_state(interaction.guild.id, interaction.user.id, numero_ava)
        self.active_avalonian_views.pop(old_key, None)
        self.active_avalonian_views[new_key] = view
        view.persist_state()

        await view.refresh_message()
        extra = f" Se libero el cupo {released_slot}." if released_slot else ""
        await interaction.response.send_message(
            f"✅ {member.mention} ahora es el caller de esta actividad.{extra}",
            ephemeral=True,
        )

    @app_commands.command(name="add")
    @app_commands.describe(
        categoria="Categoria a modificar",
        member="Usuario afectado",
        amount="Cantidad a agregar",
    )
    @app_commands.choices(categoria=CATEGORY_CHOICES)
    async def add(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        member: discord.Member,
        amount: int,
    ):
        if not self.has_economy_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True,
            )
            return

        await self.modify_balance(interaction, member, amount, categoria.value, True, "/add")

    @app_commands.command(name="remove")
    @app_commands.describe(
        categoria="Categoria a modificar",
        member="Usuario afectado",
        amount="Cantidad a remover",
    )
    @app_commands.choices(categoria=CATEGORY_CHOICES)
    async def remove(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        member: discord.Member,
        amount: int,
    ):
        if not self.has_economy_permission(interaction):
            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True,
            )
            return

        await self.modify_balance(interaction, member, amount, categoria.value, False, "/remove")

    @app_commands.command(name="add-permission")
    @app_commands.describe(
        rol="Rol que recibira permisos",
        permisos="Conjunto de permisos que recibira el rol",
    )
    @app_commands.choices(permisos=PERMISSION_CHOICES)
    async def add_permission(
        self,
        interaction: discord.Interaction,
        rol: discord.Role,
        permisos: app_commands.Choice[str],
    ):
        if not self.can_manage_permissions(interaction):
            await interaction.response.send_message(
                "No tienes permisos para gestionar roles con permisos.",
                ephemeral=True,
            )
            return

        created = self.permission_service.add_permission(interaction.guild.id, rol.id, permisos.value)
        if not created:
            await interaction.response.send_message(
                f"El rol {rol.mention} ya tiene el permiso {permisos.name}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Se agrego el permiso {permisos.name} al rol {rol.mention}."
        )

    @app_commands.command(name="remove-permission")
    @app_commands.describe(
        rol="Rol al que se le quitaran permisos",
        permisos="Conjunto de permisos que se quitara",
    )
    @app_commands.choices(permisos=PERMISSION_CHOICES)
    async def remove_permission(
        self,
        interaction: discord.Interaction,
        rol: discord.Role,
        permisos: app_commands.Choice[str],
    ):
        if not self.can_manage_permissions(interaction):
            await interaction.response.send_message(
                "No tienes permisos para gestionar roles con permisos.",
                ephemeral=True,
            )
            return

        removed = self.permission_service.remove_permission(interaction.guild.id, rol.id, permisos.value)
        if not removed:
            await interaction.response.send_message(
                f"El rol {rol.mention} no tenia el permiso {permisos.name}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Se quito el permiso {permisos.name} al rol {rol.mention}."
        )

    @config_group.command(name="canal")
    @app_commands.describe(
        tipo="Tipo de canal que quieres configurar",
        canal="Canal que se usara para esta configuracion",
    )
    @app_commands.choices(tipo=CONFIG_CHANNEL_CHOICES)
    async def config_channel(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        canal: discord.TextChannel,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Solo un administrador puede configurar canales del bot.",
                ephemeral=True,
            )
            return

        self.config_service.set_channel(interaction.guild.id, tipo.value, canal.id)
        await interaction.response.send_message(
            f"Canal configurado: **{tipo.name}** -> {canal.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="permissions")
    async def permissions(self, interaction: discord.Interaction):
        if not self.can_manage_permissions(interaction):
            await interaction.response.send_message(
                "No tienes permisos para ver los permisos del bot.",
                ephemeral=True,
            )
            return

        role_permissions = self.permission_service.get_role_permissions(interaction.guild.id)
        if not role_permissions:
            await interaction.response.send_message(
                "No hay roles con permisos configurados en este servidor.",
                ephemeral=True,
            )
            return

        lines = []
        for role_id, permissions in role_permissions.items():
            role = interaction.guild.get_role(int(role_id))
            role_name = role.mention if role else f"Rol eliminado ({role_id})"
            labels = [PERMISSION_LABELS.get(permission, permission) for permission in permissions]
            lines.append(f"{role_name}: {', '.join(labels)}")

        embed = discord.Embed(
            title="Permisos del bot",
            description="\n".join(lines),
            color=ACCENT_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
