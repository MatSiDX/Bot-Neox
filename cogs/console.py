import discord
from discord.ext import commands

from utils.console_logger import log_event


class ConsoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def describe_interaction(self, interaction):
        user = getattr(interaction, "user", None)
        guild = getattr(interaction, "guild", None)
        user_name = f"{user} ({user.id})" if user else "Usuario desconocido"
        guild_name = f"{guild.name} ({guild.id})" if guild else "DM"
        return user_name, guild_name

    def format_option_value(self, value):
        if isinstance(value, (discord.Member, discord.User)):
            return f"{value.display_name} ({value.id})"
        if isinstance(value, discord.Role):
            return f"@{value.name} ({value.id})"
        return str(value)

    def describe_options(self, interaction):
        namespace = getattr(interaction, "namespace", None)
        if not namespace:
            return "sin parametros"

        options = vars(namespace)
        if not options:
            return "sin parametros"

        return ", ".join(
            f"{name}={self.format_option_value(value)}"
            for name, value in options.items()
        )

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction, command):
        user_name, guild_name = self.describe_interaction(interaction)
        options = self.describe_options(interaction)
        log_event(
            f"COMANDO OK /{command.qualified_name} | Parametros: {options} | Usuario: {user_name} | Servidor: {guild_name}"
        )

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction, error):
        command_name = interaction.command.qualified_name if interaction.command else "desconocido"
        user_name, guild_name = self.describe_interaction(interaction)
        options = self.describe_options(interaction)
        log_event(
            f"COMANDO ERROR /{command_name} | Parametros: {options} | Usuario: {user_name} | Servidor: {guild_name} | Error: {error}"
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type not in (discord.InteractionType.component, discord.InteractionType.modal_submit):
            return

        user_name, guild_name = self.describe_interaction(interaction)
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "sin custom_id") if interaction.data else "sin custom_id"
            log_event(f"BOTON {custom_id} | Usuario: {user_name} | Servidor: {guild_name}")
            return

        log_event(f"MODAL enviado | Usuario: {user_name} | Servidor: {guild_name}")


async def setup(bot):
    await bot.add_cog(ConsoleCog(bot))
