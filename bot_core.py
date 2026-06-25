import discord
from discord.ext import commands

from config.settings import BOT_SETTINGS


class ProjectBot(commands.Bot):
    def __init__(self, *, cogs, **kwargs):
        super().__init__(**kwargs)
        self.cogs_to_load = list(cogs)

    async def setup_hook(self):
        for extension in self.cogs_to_load:
            await self.load_extension(extension)
        await self.tree.sync()


def build_bot(*, cogs, command_prefix="%", enable_message_content=None):
    intents = discord.Intents.default()
    if enable_message_content is None:
        enable_message_content = BOT_SETTINGS.enable_message_content_intent
    intents.message_content = enable_message_content
    intents.members = BOT_SETTINGS.enable_member_intent
    intents.voice_states = BOT_SETTINGS.enable_voice_intent
    return ProjectBot(command_prefix=command_prefix, intents=intents, cogs=cogs)
