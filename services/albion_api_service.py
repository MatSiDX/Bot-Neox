import asyncio

import aiohttp


class AlbionApiError(RuntimeError):
    pass


class AlbionApiService:
    BASE_URL = "https://gameinfo.albiononline.com/api/gameinfo"

    def __init__(self, *, timeout_seconds=15, max_attempts=3):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_attempts = max(1, int(max_attempts))

    async def _get_json(self, path, *, params=None):
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "AvalonBot/1.0 Albion registration",
        }
        last_error = None
        for attempt in range(self.max_attempts):
            try:
                async with aiohttp.ClientSession(
                    timeout=self.timeout,
                    headers=headers,
                ) as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 404:
                            return None
                        if response.status == 200:
                            return await response.json(content_type=None)
                        if response.status == 429 or response.status >= 500:
                            retry_after = response.headers.get("Retry-After")
                            try:
                                delay = max(0.0, min(float(retry_after), 5.0))
                            except (TypeError, ValueError):
                                delay = min(1.0 + attempt, 3.0)
                            last_error = AlbionApiError(
                                f"La API de Albion respondio con estado {response.status}."
                            )
                            if attempt + 1 < self.max_attempts:
                                await asyncio.sleep(delay)
                                continue
                        raise AlbionApiError(
                            f"La API de Albion respondio con estado {response.status}."
                        )
            except asyncio.TimeoutError as exc:
                last_error = AlbionApiError(
                    "La API de Albion tardo demasiado en responder."
                )
                if attempt + 1 >= self.max_attempts:
                    raise last_error from exc
            except aiohttp.ClientError as exc:
                last_error = AlbionApiError(
                    "No se pudo conectar con la API de Albion."
                )
                if attempt + 1 >= self.max_attempts:
                    raise last_error from exc
            except (ValueError, TypeError) as exc:
                raise AlbionApiError(
                    "La API de Albion devolvio una respuesta invalida."
                ) from exc

            if attempt + 1 < self.max_attempts:
                await asyncio.sleep(min(1.0 + attempt, 3.0))

        raise last_error or AlbionApiError("No se pudo consultar la API de Albion.")

    async def search(self, query):
        data = await self._get_json("search", params={"q": str(query).strip()})
        return data if isinstance(data, dict) else {}

    async def find_player_exact(self, player_name):
        clean_name = str(player_name or "").strip()
        if not clean_name:
            return None

        data = await self.search(clean_name)
        candidates = data.get("players", []) if isinstance(data.get("players"), list) else []
        exact = [
            player
            for player in candidates
            if str(player.get("Name") or "").casefold() == clean_name.casefold()
        ]
        if not exact:
            return None

        exact.sort(key=lambda player: str(player.get("Name") or ""))
        return exact[0]

    async def find_guild_exact(self, guild_name):
        clean_name = str(guild_name or "").strip()
        if not clean_name:
            return None

        data = await self.search(clean_name)
        candidates = data.get("guilds", []) if isinstance(data.get("guilds"), list) else []
        exact = [
            guild
            for guild in candidates
            if str(guild.get("Name") or "").casefold() == clean_name.casefold()
        ]
        if not exact:
            return None

        exact.sort(key=lambda guild: str(guild.get("Name") or ""))
        return exact[0]

    async def get_player(self, player_id):
        data = await self._get_json(f"players/{player_id}")
        return data if isinstance(data, dict) else None
