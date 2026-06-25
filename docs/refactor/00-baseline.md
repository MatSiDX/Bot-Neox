# Fase 0 - Baseline Tecnico

Fecha de baseline: 2026-06-18

## Objetivo

Dejar una fotografia tecnica inicial del proyecto antes de cualquier refactor estructural. Esta fase no cambia comportamiento del bot, del dashboard ni de la persistencia.

## Restricciones activas

- No refactorizar `web_dashboard.py` en esta fase.
- No crear `src/neox` todavia.
- No eliminar `bot_secondary.py`, `run_both.py` ni `secondary_cogs/`.
- No migrar SQLite, JSON ni slash commands.
- No ejecutar el bot contra Discord como parte de esta fase.
- No exponer secretos, sesiones, tokens ni contenido de `.env`.

## Puntos de entrada actuales

- `bot.py`: arranque del bot principal de economia.
- `bot_secondary.py`: arranque del bot secundario.
- `run_both.py`: arranque conjunto de bot principal y bot secundario.
- `bot_manager.py`: consola local que administra bot principal y dashboard.
- `web_dashboard.py`: dashboard web local monolitico.

## Estructura actual relevante

- `cogs/`: comandos slash y comportamiento principal del bot.
- `secondary_cogs/`: extensiones del bot secundario.
- `services/`: logica de dominio y coordinacion.
- `repositories/`: acceso a SQLite y archivos JSON.
- `views/`: vistas y componentes de Discord.
- `utils/`: helpers compartidos.
- `config/`: carga de configuracion desde entorno.
- `scripts/`: scripts operativos y de mantenimiento.
- `tests/`: baseline de pruebas automatizadas existente.
- `data/`: artefactos runtime, base SQLite, sesiones, logs y JSON.

## Baseline observado

- `web_dashboard.py` concentra 8417 lineas y hoy es el punto de mayor acoplamiento estructural.
- Existen 5 archivos de pruebas en `tests/`.
- Dependencias declaradas en `requirements.txt`: `discord.py`, `aiohttp`, `openpyxl`, `python-dotenv`.
- La configuracion central de entorno se concentra en `config/settings.py`.
- La persistencia actual combina SQLite (`data/bot.sqlite3`) con multiples archivos JSON bajo `data/`.

## Persistencia actual

SQLite:

- `data/bot.sqlite3`
- `data/bot.sqlite3-wal`
- `data/bot.sqlite3-shm`

JSON/runtime identificados:

- `data/balances.json`
- `data/operations.json`
- `data/config.json`
- `data/permissions.json`
- `data/ping_templates.json`
- `data/reports.json`
- `data/report_runtime.json`
- `data/report_dashboard_requests.json`
- `data/active_avalonian_pings.json`
- `data/avalonian_interactions.json`
- `data/audit_events.json`
- `data/dashboard_sessions.json`

Otros artefactos runtime:

- `data/dashboard.log`
- `data/dashboard.err`
- `data/fine_proofs/`

## Artefactos sensibles o no aptos para repo/ZIP

No versionar ni compartir en entregables:

- `.env`
- Cualquier `.env.*` real distinto de `.env.example`
- `data/bot.sqlite3`, `data/bot.sqlite3-wal`, `data/bot.sqlite3-shm`
- `data/dashboard_sessions.json`
- Logs runtime en `data/`
- Evidencias en `data/fine_proofs/`
- JSON operativos de `data/` con informacion de servidores, usuarios o actividad
- `__pycache__/` y bytecode Python
- Entornos virtuales locales

## Estado del arbol de trabajo al iniciar Fase 0

Se detectaron cambios locales previos en:

- `bot.py`
- `cogs/console.py`
- `config/settings.py`

Esta fase evita sobrescribir esos cambios funcionales y trabaja solo en documentacion y utilidades seguras.

## Validacion minima definida para el baseline

- Compilacion estatica del arbol Python:
  - `python -m compileall .`
- Descubrimiento y ejecucion de pruebas existentes:
  - `python -m unittest discover -s tests -v`
- Script auxiliar seguro:
  - `python scripts/validate_local.py`

## Resultado esperado de Fase 0

- Documentacion inicial del estado actual.
- Checklist de validacion local sin conectar a Discord.
- Checklist incremental de fases del refactor.
- Identificacion explicita de artefactos sensibles y runtime que no deben versionarse.
