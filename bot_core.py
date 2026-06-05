import discord
from discord.ext import commands


class ProjectBot(commands.Bot):
    def __init__(self, *, cogs, **kwargs):
        super().__init__(**kwargs)
        self.cogs_to_load = list(cogs)

    async def setup_hook(self):
        for extension in self.cogs_to_load:
            await self.load_extension(extension)
        await self.tree.sync()


def build_bot(*, cogs, command_prefix="%", enable_message_content=True):
    intents = discord.Intents.default()
    intents.message_content = enable_message_content
    return ProjectBot(command_prefix=command_prefix, intents=intents, cogs=cogs)
