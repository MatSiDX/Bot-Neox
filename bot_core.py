import discord
from discord.ext import commands

from config.settings import BOT_SETTINGS
from utils.console_logger import configure_logging, log_event, log_exception
from utils.interaction_safety import SafeCommandTree, configure_asyncio_exception_handler


class ProjectBot(commands.Bot):
    def __init__(self, *, cogs, **kwargs):
        super().__init__(**kwargs)
        self.cogs_to_load = list(cogs)

    async def setup_hook(self):
        configure_asyncio_exception_handler(self.loop)
        for extension in self.cogs_to_load:
            try:
                await self.load_extension(extension)
                log_event(f"Cog cargado: {extension}")
            except Exception as exc:
                log_exception(f"No pude cargar el cog {extension}", exc)
                raise
        synced = await self.tree.sync()
        log_event(f"Slash commands sincronizados: {len(synced)}")

    async def on_error(self, event_method, *args, **kwargs):
        log_exception(f"Error no controlado en evento {event_method}")

    async def on_command_error(self, context, exception):
        log_exception(f"Error en comando prefijo {getattr(context.command, 'qualified_name', 'desconocido')}", exception)


def build_bot(*, cogs, command_prefix=commands.when_mentioned, enable_message_content=None):
    configure_logging()
    intents = discord.Intents.default()
    if enable_message_content is None:
        enable_message_content = BOT_SETTINGS.enable_message_content_intent
    intents.message_content = enable_message_content
    intents.members = BOT_SETTINGS.enable_member_intent
    intents.voice_states = BOT_SETTINGS.enable_voice_intent
    return ProjectBot(command_prefix=command_prefix, intents=intents, cogs=cogs, tree_cls=SafeCommandTree)
