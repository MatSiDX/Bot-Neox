import discord
from discord.ext import commands
from discord import app_commands


class SecondaryCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bot-info", description="Ver informacion basica del bot Niveles")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.send_message("Bot Niveles activo.")


async def setup(bot):
    await bot.add_cog(SecondaryCore(bot))
