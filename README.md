# Bot-Neox

Bot de Discord en Python + `discord.py` con dashboard web liviano, persistencia SQLite/JSON y refactor estructural progresivo ya consolidado.

## Estado Actual

- Un solo bot oficial de Discord
- Dashboard mantenido con el stack web actual
- SQLite como persistencia principal
- JSON legacy conservados donde aun aplica compatibilidad temporal
- Estructura progresiva en `src/neox`

## Requisitos

```text
Python 3.11 o superior
```

Instalacion local:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Despues crea `.env` a partir de `.env.example`.

## Inicio Rapido

Bot + consola de control + dashboard:

```bat
run.bat
```

Solo bot:

```bat
python bot.py
```

Solo dashboard:

```bat
run_dashboard.bat
```

o:

```bat
python web_dashboard.py --host 127.0.0.1 --port 8000
```

Dashboard local:

```text
http://127.0.0.1:8000/dashboard
```

## Variables De Entorno

Variables principales:

- `TOKEN`: token principal del bot
- `ECONOMY_TOKEN`: alias compatible del token del bot
- `DASHBOARD_SESSION_SECRET`: secreto obligatorio para sesiones del dashboard
- `DASHBOARD_CLIENT_ID`: cliente OAuth del dashboard
- `DASHBOARD_CLIENT_SECRET`: secreto OAuth del dashboard
- `DASHBOARD_REDIRECT_URI`: callback OAuth
- `DASHBOARD_PUBLIC_URL`: URL publica base del dashboard

Variables adicionales y TTL de metadata estan documentadas en:

- [docs/operations.md](docs/operations.md)
- [.env.example](.env.example)

## Validaciones Locales

Validaciones seguras que no arrancan el bot ni lo conectan a Discord:

```bat
python -m compileall .
python -m unittest discover -s tests -v
python scripts\validate_local.py
python -m pytest
```

Notas:

- `unittest discover` ya omite pruebas dependientes de `discord.py` o `aiohttp` cuando esas dependencias no estan instaladas.
- `scripts\validate_local.py` ejecuta una suite unitaria segura, `compileall`, `unittest discover` y `pytest` si esta disponible.

## Estructura Del Proyecto

```text
bot.py
web_dashboard.py
config/
repositories/
services/
cogs/
src/neox/
  config/
  core/
  dashboard/
docs/
tests/
```

Resumen:

- `bot.py`: entrypoint principal del bot
- `web_dashboard.py`: entrypoint actual del dashboard
- `src/neox/core`: servicios, repositorios y dominio compartido
- `src/neox/dashboard/templates`: templates HTML
- `src/neox/dashboard/static`: CSS y JavaScript del dashboard

## Persistencia, Migraciones y Backups

Persistencia principal:

- SQLite runtime: `data/bot.sqlite3`
- JSON legacy/runtime: `data/*.json`

Scripts utiles:

```bat
python scripts\backup_database.py
python scripts\migrate_economy_to_sqlite.py
python scripts\import_economy_data.py
python scripts\import_balance_names.py
```

Backups recomendados antes de cambios estructurales:

- `data/bot.sqlite3`
- `data/bot.sqlite3-wal`
- `data/bot.sqlite3-shm`
- `data/config.json`
- `data/permissions.json`
- `data/ping_templates.json`
- `data/dashboard_sessions.json`

## JSON Legacy

Estado actual:

- `config.json` y `permissions.json` ya migran progresivamente a SQLite con compatibilidad temporal.
- Los JSON legacy no se borran automaticamente.
- El proyecto mantiene estrategia conservadora: `SQLite primero`, fallback/backfill controlado y dual-write donde corresponde.

## Operacion y Checklists

Documentacion operativa:

- [docs/operations.md](docs/operations.md)
- [docs/smoke-test-checklist.md](docs/smoke-test-checklist.md)
- [docs/release-checklist.md](docs/release-checklist.md)

## Documentacion Del Refactor

- [docs/refactor/03-phases-checklist.md](docs/refactor/03-phases-checklist.md)
- [docs/refactor/04-src-neox-layout.md](docs/refactor/04-src-neox-layout.md)
- [docs/refactor/05-core-shared-layer.md](docs/refactor/05-core-shared-layer.md)
- [docs/refactor/06-dashboard-map.md](docs/refactor/06-dashboard-map.md)
- [docs/refactor/07-dashboard-assets.md](docs/refactor/07-dashboard-assets.md)
- [docs/refactor/08-dashboard-initial-load.md](docs/refactor/08-dashboard-initial-load.md)
- [docs/refactor/09-dashboard-lazy-views.md](docs/refactor/09-dashboard-lazy-views.md)
- [docs/refactor/10-discord-metadata-cache.md](docs/refactor/10-discord-metadata-cache.md)
- [docs/refactor/11-dashboard-action-requests.md](docs/refactor/11-dashboard-action-requests.md)
- [docs/refactor/12-json-to-sqlite-phase1.md](docs/refactor/12-json-to-sqlite-phase1.md)
- [docs/refactor/13-permissions-hardening.md](docs/refactor/13-permissions-hardening.md)
- [docs/refactor/14-finalization.md](docs/refactor/14-finalization.md)
