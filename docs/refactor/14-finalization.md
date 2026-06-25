# Fase 14 - Tests, Limpieza Final y Documentacion

Fecha de actualizacion: 2026-06-18

## Objetivo

Cerrar el refactor estructural con:

- documentacion operativa clara
- pruebas unitarias reforzadas
- limpieza de referencias obsoletas confirmadas
- reglas de versionado mas seguras para runtime y secretos

## Limpieza Aplicada

- Se retiro `src/neox/dashboard/entrypoints.py` porque ya no tenia referencias vivas.
- Se mantuvieron los entrypoints reales:
  - `bot.py`
  - `web_dashboard.py`
  - `run.bat`
  - `run_dashboard.bat`

## Tests Reforzados

Se agregaron o mejoraron pruebas para:

- configuracion centralizada
- paginacion
- repositorio de `dashboard_action_requests`
- compatibilidad de wrappers
- migracion JSON -> SQLite
- permisos centralizados
- helpers del dashboard
- cache de metadata de Discord

Ademas, las pruebas que requieren `discord.py` o `aiohttp` ahora se omiten limpiamente si esas dependencias no estan instaladas.

## Documentacion Consolidada

Nuevos documentos:

- `docs/operations.md`
- `docs/smoke-test-checklist.md`
- `docs/release-checklist.md`

README ahora actua como punto de entrada corto y enlaza a la documentacion operativa.

## Estado Final Del Refactor

- Bot unico
- Configuracion centralizada
- `src/neox` creado y usado progresivamente
- Core compartido inicial
- Dashboard modularizado sin cambio de stack
- Carga inicial reducida y vistas lazy
- Paginacion progresiva
- Cache de metadata de Discord
- Cola de solicitudes dashboard -> bot
- Migracion progresiva de JSON criticos a SQLite
- Permisos centralizados y endurecimiento de seguridad

## Pendientes Fuera De Esta Fase

- mover mas pruebas de integracion a entornos con `discord.py` y `aiohttp`
- continuar migraciones JSON -> SQLite en bloques de bajo riesgo
- evaluar wrappers legacy remanentes cuando dejen de tener consumidores reales
