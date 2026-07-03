import discord
from discord import app_commands
from discord.ext import commands

from services.music_service import MusicError, MusicService, QueueFullError


SAME_CHANNEL_REQUIRED_MESSAGE = (
    "Ya estoy usando musica en {channel}. En un mismo servidor no puedo estar en dos canales de voz a la vez; "
    "entra a ese canal para controlar esa sesion o desconectame desde ahi."
)


class MusicCog(commands.Cog):
    music = app_commands.Group(name="musica", description="Control de musica del servidor")

    def __init__(self, bot):
        self.bot = bot
        self.service = MusicService(bot)

    def cog_unload(self):
        self.bot.loop.create_task(self.service.close())

    async def _get_author_voice_channel(self, interaction: discord.Interaction):
        if interaction.guild is None:
            raise MusicError("Este comando solo se puede usar dentro de un servidor.")

        voice_state = getattr(interaction.user, "voice", None)
        channel = getattr(voice_state, "channel", None)
        if channel is None:
            raise MusicError("Primero entra a un canal de voz.")
        return channel

    async def _ensure_voice_client(self, interaction: discord.Interaction):
        channel = await self._get_author_voice_channel(interaction)
        guild = interaction.guild
        assert guild is not None

        permissions = channel.permissions_for(guild.me)
        if not permissions.connect:
            raise MusicError("No tengo permiso para conectarme a tu canal de voz.")
        if not permissions.speak:
            raise MusicError("No tengo permiso para hablar en tu canal de voz.")

        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected():
            if voice_client.channel and voice_client.channel.id != channel.id:
                raise MusicError(SAME_CHANNEL_REQUIRED_MESSAGE.format(channel=voice_client.channel.mention))
            return voice_client

        try:
            return await channel.connect(self_deaf=True)
        except RuntimeError as exc:
            raise MusicError(
                "No puedo usar voz porque faltan dependencias del entorno. "
                "Instala `discord.py[voice]` o ejecuta `pip install -r requirements.txt`."
            ) from exc

    async def _get_player_for_author_channel(self, interaction: discord.Interaction):
        channel = await self._get_author_voice_channel(interaction)
        guild = interaction.guild
        assert guild is not None

        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected() and voice_client.channel and voice_client.channel.id != channel.id:
            raise MusicError(SAME_CHANNEL_REQUIRED_MESSAGE.format(channel=voice_client.channel.mention))

        player = self.service.players.get(guild.id)
        if player and player.voice_client and player.voice_client.channel and player.voice_client.channel.id != channel.id:
            raise MusicError(SAME_CHANNEL_REQUIRED_MESSAGE.format(channel=player.voice_client.channel.mention))
        return player

    async def _send_error(self, interaction: discord.Interaction, message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @music.command(name="play", description="Reproduce una URL o busca una cancion")
    @app_commands.describe(consulta="URL o busqueda de YouTube")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, consulta: str):
        await interaction.response.defer(thinking=True)

        try:
            voice_client = await self._ensure_voice_client(interaction)
            track = await self.service.extract_track(consulta, interaction.user)
            player = self.service.get_player(interaction.guild.id)
            position = await player.enqueue(track, voice_client, interaction.channel)
        except QueueFullError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except (MusicError, discord.ClientException, discord.Forbidden, discord.HTTPException) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if position <= 1:
            await interaction.followup.send(f"Agregue **{track.title}** y empece la reproduccion.")
        else:
            await interaction.followup.send(f"Agregue **{track.title}** a la cola en posicion {position}.")

    @music.command(name="pause", description="Pausa la reproduccion actual")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player or not await player.pause():
            await self._send_error(interaction, "No hay una cancion reproduciendose para pausar.")
            return
        await interaction.response.send_message("Musica pausada.")

    @music.command(name="resume", description="Reanuda la reproduccion pausada")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player or not await player.resume():
            await self._send_error(interaction, "No hay una cancion pausada para reanudar.")
            return
        await interaction.response.send_message("Musica reanudada.")

    @music.command(name="skip", description="Salta la cancion actual")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player or not await player.skip():
            await self._send_error(interaction, "No hay una cancion reproduciendose para saltar.")
            return
        await interaction.response.send_message("Saltando cancion.")

    @music.command(name="stop", description="Detiene la reproduccion y limpia la cola")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player:
            await self._send_error(interaction, "No hay musica activa en este servidor.")
            return
        await player.stop(clear_queue=True, disconnect=False)
        await interaction.response.send_message("Reproduccion detenida y cola limpiada.")

    @music.command(name="queue", description="Muestra la cola de musica")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player:
            await self._send_error(interaction, "La cola esta vacia.")
            return

        status = await player.status()
        lines = []
        if status.current:
            paused = " (pausada)" if status.paused else ""
            lines.append(f"Ahora: **{status.current.title}** - {status.current.duration_label}{paused}")

        if status.queued:
            for index, track in enumerate(status.queued[:10], start=1):
                lines.append(f"{index}. **{track.title}** - {track.duration_label}")
            remaining = len(status.queued) - 10
            if remaining > 0:
                lines.append(f"... y {remaining} mas.")

        if not lines:
            await self._send_error(interaction, "La cola esta vacia.")
            return

        await interaction.response.send_message("\n".join(lines))

    @music.command(name="clear", description="Limpia las canciones pendientes")
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        if not player:
            await self._send_error(interaction, "La cola ya esta vacia.")
            return

        removed = await player.clear_queue()
        await interaction.response.send_message(f"Limpie {removed} canciones pendientes.")

    @music.command(name="disconnect", description="Desconecta al bot del canal de voz")
    @app_commands.guild_only()
    async def disconnect(self, interaction: discord.Interaction):
        try:
            player = await self._get_player_for_author_channel(interaction)
        except MusicError as exc:
            await self._send_error(interaction, str(exc))
            return
        voice_client = interaction.guild.voice_client
        if not player and not voice_client:
            await self._send_error(interaction, "No estoy conectado a un canal de voz.")
            return

        if player:
            await player.stop(clear_queue=True, disconnect=True)
        elif voice_client:
            await voice_client.disconnect(force=True)

        await interaction.response.send_message("Me desconecte y limpie los recursos de musica.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id != self.bot.user.id:
            return
        if before.channel and after.channel is None:
            voice_client = member.guild.voice_client
            if voice_client:
                await self.service.on_voice_disconnect(voice_client)
            else:
                player = self.service.players.get(member.guild.id)
                if player:
                    await player.stop(clear_queue=True, disconnect=False)


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
