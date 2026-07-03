from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque

import discord
import yt_dlp


class _YtdlpLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        logging.getLogger("bot.music.ytdlp").error(message)


YTDLP_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "logger": _YtdlpLogger(),
    "default_search": "ytsearch",
    "extract_flat": False,
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

MAX_QUEUE_SIZE = 100
PLAYER_IDLE_TIMEOUT_SECONDS = 300


class MusicError(Exception):
    pass


class QueueFullError(MusicError):
    pass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str
    duration: int | None
    requested_by_id: int
    requested_by_name: str

    @property
    def duration_label(self):
        if not self.duration:
            return "duracion desconocida"
        minutes, seconds = divmod(int(self.duration), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass
class PlayerStatus:
    current: Track | None
    queued: list[Track]
    paused: bool
    connected_channel_id: int | None


class GuildMusicPlayer:
    def __init__(self, guild_id: int, bot: object, service: "MusicService"):
        self.guild_id = guild_id
        self.bot = bot
        self.service = service
        self.queue: Deque[Track] = deque()
        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.abc.Messageable | None = None
        self.current: Track | None = None
        self.next_track = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.stopping = False
        self.skip_requested = False

    async def enqueue(self, track: Track, voice_client: discord.VoiceClient, text_channel: discord.abc.Messageable):
        async with self.lock:
            if len(self.queue) >= MAX_QUEUE_SIZE:
                raise QueueFullError(f"La cola llego al maximo de {MAX_QUEUE_SIZE} canciones.")
            self.voice_client = voice_client
            self.text_channel = text_channel
            self.queue.append(track)
            if self.task is None or self.task.done():
                self.stopping = False
                self.task = asyncio.create_task(self.run(), name=f"music-player-{self.guild_id}")
            position = len(self.queue)
            if self.current is None and not voice_client.is_playing() and not voice_client.is_paused():
                position = 1
            return position

    async def run(self):
        try:
            while not self.stopping:
                try:
                    track = await asyncio.wait_for(self._pop_next_track(), timeout=PLAYER_IDLE_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    await self.disconnect()
                    break

                track = await self.service.refresh_track_stream(track)
                self.current = track
                self.next_track.clear()
                self.skip_requested = False

                if not self.voice_client or not self.voice_client.is_connected():
                    await self._send_text("Me desconecte del canal de voz. Limpie la cola de musica.")
                    await self.stop(clear_queue=True, disconnect=False)
                    break

                source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
                self.voice_client.play(source, after=self._after_playback)
                await self._send_text(f"Reproduciendo ahora: **{track.title}** ({track.duration_label})")
                await self.next_track.wait()

                if self.skip_requested:
                    await self._send_text("Cancion saltada.")

                self.current = None
        except Exception as exc:
            logging.getLogger("bot.music").exception("Error en reproductor de guild %s", self.guild_id)
            await self._send_text(f"Ocurrio un error de reproduccion: `{type(exc).__name__}`. Limpie la cola.")
            await self.stop(clear_queue=True, disconnect=False)
        finally:
            self.current = None
            self.service.release_if_idle(self.guild_id, self)

    async def _pop_next_track(self):
        while not self.stopping:
            async with self.lock:
                if self.queue:
                    return self.queue.popleft()
            await asyncio.sleep(0.25)
        raise asyncio.CancelledError

    def _after_playback(self, error: Exception | None):
        if error:
            logging.getLogger("bot.music").error("FFmpeg fallo en guild %s: %s", self.guild_id, error)
        self.bot.loop.call_soon_threadsafe(self.next_track.set)

    async def pause(self):
        if not self.voice_client or not self.voice_client.is_playing():
            return False
        self.voice_client.pause()
        return True

    async def resume(self):
        if not self.voice_client or not self.voice_client.is_paused():
            return False
        self.voice_client.resume()
        return True

    async def skip(self):
        if not self.voice_client or not (self.voice_client.is_playing() or self.voice_client.is_paused()):
            return False
        self.skip_requested = True
        self.voice_client.stop()
        return True

    async def stop(self, *, clear_queue=True, disconnect=False):
        self.stopping = disconnect
        self.skip_requested = False
        async with self.lock:
            if clear_queue:
                self.queue.clear()
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
        self.next_track.set()
        if disconnect:
            await self.disconnect()

    async def disconnect(self):
        voice_client = self.voice_client
        self.voice_client = None
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect(force=True)

    async def clear_queue(self):
        async with self.lock:
            count = len(self.queue)
            self.queue.clear()
            return count

    async def status(self):
        async with self.lock:
            queued = list(itertools.islice(self.queue, 0, MAX_QUEUE_SIZE))
        channel_id = getattr(getattr(self.voice_client, "channel", None), "id", None)
        paused = bool(self.voice_client and self.voice_client.is_paused())
        return PlayerStatus(
            current=self.current,
            queued=queued,
            paused=paused,
            connected_channel_id=channel_id,
        )

    async def handle_voice_disconnect(self, voice_client: discord.VoiceClient):
        if self.voice_client is not voice_client:
            return
        await self.stop(clear_queue=True, disconnect=False)
        self.voice_client = None

    async def _send_text(self, message: str):
        if not self.text_channel:
            return
        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await self.text_channel.send(message)


class MusicService:
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, GuildMusicPlayer] = {}
        self.ytdlp = yt_dlp.YoutubeDL(YTDLP_OPTIONS)

    def get_player(self, guild_id: int):
        player = self.players.get(guild_id)
        if player is None:
            player = GuildMusicPlayer(guild_id, self.bot, self)
            self.players[guild_id] = player
        return player

    async def extract_track(self, query: str, requested_by: discord.abc.User):
        data = await asyncio.to_thread(self._extract_info, query)
        return self._track_from_data(data, query, requested_by)

    async def refresh_track_stream(self, track: Track):
        data = await asyncio.to_thread(self._extract_info, track.webpage_url)
        return self._track_from_data(
            data,
            track.webpage_url,
            _RequestedBy(track.requested_by_id, track.requested_by_name),
        )

    def _track_from_data(self, data: dict, query: str, requested_by: discord.abc.User):
        entries = data.get("entries")
        if entries:
            data = next((entry for entry in entries if entry), None)
        if not data:
            raise MusicError("No encontre resultados para esa busqueda.")

        stream_url = data.get("url")
        webpage_url = data.get("webpage_url") or data.get("original_url") or query
        title = data.get("title") or webpage_url
        if not stream_url:
            raise MusicError("No pude obtener una fuente de audio reproducible.")

        return Track(
            title=title,
            webpage_url=webpage_url,
            stream_url=stream_url,
            duration=data.get("duration"),
            requested_by_id=requested_by.id,
            requested_by_name=getattr(requested_by, "display_name", str(requested_by)),
        )

    def _extract_info(self, query: str):
        try:
            return self.ytdlp.extract_info(query, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise MusicError("No pude extraer audio de esa URL o busqueda.") from exc

    def release_if_idle(self, guild_id: int, player: GuildMusicPlayer):
        current = self.players.get(guild_id)
        if current is player and player.current is None and not player.queue:
            self.players.pop(guild_id, None)

    async def close(self):
        players = list(self.players.values())
        self.players.clear()
        await asyncio.gather(
            *(player.stop(clear_queue=True, disconnect=True) for player in players),
            return_exceptions=True,
        )

    async def on_voice_disconnect(self, voice_client: discord.VoiceClient):
        guild = getattr(voice_client, "guild", None)
        if guild is None:
            return
        player = self.players.get(guild.id)
        if player:
            await player.handle_voice_disconnect(voice_client)


@dataclass(frozen=True)
class _RequestedBy:
    id: int
    display_name: str
