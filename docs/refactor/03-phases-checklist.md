# Checklist De Refactor Por Fases

## Fase 0 - Baseline y preparacion

- [x] Documentar baseline tecnico.
- [x] Documentar mapa de riesgos.
- [x] Documentar validaciones locales seguras.
- [x] Identificar artefactos sensibles y runtime que no deben versionarse.
- [x] Agregar script seguro de validacion local.

## Fase 1 - Bot unico oficial

- [x] Retirar la dependencia operativa del bot secundario.
- [x] Migrar la funcionalidad util del bot secundario al bot principal.
- [x] Eliminar la necesidad de `SECONDARY_TOKEN`.
- [x] Actualizar entry points, configuracion y documentacion a una sola instancia oficial del bot.

## Fase 2 - Centralizacion de configuracion

- [x] Centralizar lectura de variables de entorno en `config/settings.py`.
- [x] Separar configuracion del bot y del dashboard.
- [x] Eliminar el fallback de `DASHBOARD_SESSION_SECRET` al token del bot.
- [x] Centralizar paths compartidos de runtime y SQLite.
- [x] Mantener compatibilidad con `TOKEN`, `ECONOMY_TOKEN`, `DASHBOARD_CLIENT_ID` y `DASHBOARD_CLIENT_SECRET`.

## Fase 3 - Base `src/neox`

- [x] Crear la estructura base `src/neox`.
- [x] Mantener `bot.py` y `web_dashboard.py` como entrypoints actuales.
- [x] Mover solo la capa de configuracion detras de un wrapper compatible.
- [x] Agregar wrappers minimos para bot y dashboard futuros.

## Fase 4 - Core compartido inicial

- [x] Mover servicios puros compartidos a `src/neox/core/services`.
- [x] Mover repositorios puros compartidos a `src/neox/core/repositories`.
- [x] Mantener wrappers compatibles en las rutas antiguas.
- [x] Evitar dependencias de `discord.py` y del dashboard dentro de `core`.

## Fase 5 - Primer corte del dashboard

- [x] Extraer helpers puros del dashboard a modulos auxiliares.
- [x] Mantener `web_dashboard.py` como entry point estable.
- [x] Mantener sin cambios las rutas publicas, OAuth y sesiones.
- [x] Documentar el mapa del dashboard y el primer corte aplicado.

## Fase 6 - Extraccion de templates y assets del dashboard

- [x] Extraer el HTML principal del dashboard a templates.
- [x] Extraer CSS embebido a archivos estaticos.
- [x] Extraer JavaScript embebido a archivos estaticos.
- [x] Mantener `web_dashboard.py` como entrypoint operativo.
- [x] Documentar como se sirven los assets estaticos.

## Fase 7 - Reduccion de carga inicial del dashboard

- [x] Separar bootstrap minimo de carga por modulo.
- [x] Crear endpoints minimos para sesion, guilds y permisos base.
- [x] Evitar la carga inicial de economia, tickets, Albion, auditoria, plantillas y metadata pesada.
- [x] Mantener compatibilidad con endpoints legacy mientras se completa la migracion progresiva.

## Fase 8 - Carga lazy por vista en el dashboard

- [x] Separar loaders por vista en archivos JS propios.
- [x] Agregar un router ligero para la navegacion interna del dashboard.
- [x] Hacer que cada vista llame solo a sus endpoints al abrirse.
- [x] Evitar el render global de todos los modulos al mismo tiempo.

## Fase 9 - Paginacion y filtros

- [x] Agregar paginacion a listas grandes del dashboard.
- [x] Unificar respuesta paginada con `items`, `page`, `page_size`, `total_items` y `total_pages`.
- [x] Incorporar filtros basicos por texto, estado, tipo y fecha.
- [x] Evitar la carga completa en memoria para vistas grandes.

## Fase 10 - Cache de metadata de Discord

- [x] Agregar cache por guild para roles, canales, categorias y emojis.
- [x] Usar TTL por tipo de metadata.
- [x] Mantener refresh e invalidacion controlada.
- [x] Reducir llamadas repetidas a Discord desde el dashboard.

## Fase 11 - Cola dashboard -> bot

- [x] Crear la infraestructura `dashboard_action_requests` en SQLite.
- [x] Crear repositorio y servicio para solicitudes.
- [x] Preparar worker del bot con reclamacion segura.
- [x] Mantener compatibilidad temporal del dashboard mientras migra acciones.

## Fase 12 - JSON criticos a SQLite

- [x] Migrar progresivamente `config.json`.
- [x] Migrar progresivamente `permissions.json`.
- [x] Mantener fallback/backfill temporal a JSON.
- [x] Documentar backups y reversion.

## Fase 13 - Permisos y seguridad

- [x] Centralizar permisos por modulo.
- [x] Aplicar `deny-by-default`.
- [x] Endurecer endpoints sensibles del dashboard.
- [x] Registrar cambios administrativos del dashboard en auditoria.

## Fase 14 - Tests, limpieza final y documentacion

- [x] Consolidar README y documentacion operativa.
- [x] Agregar checklist de smoke test y release limpio.
- [x] Mejorar cobertura unitaria de configuracion, paginacion, repositorios y permisos.
- [x] Hacer que pruebas dependientes de `discord.py`/`aiohttp` se omitan limpiamente si faltan esas dependencias.
- [x] Retirar archivos obsoletos confirmados sin referencias vivas.
- [x] Reforzar `.gitignore` para secretos y runtime.

## Criterio transversal

Cada fase debe cerrar con:

- `python -m compileall .`
- `python -m unittest discover -s tests -v` si el entorno lo permite
- `python -m pytest` si esta disponible
- cero cambios deliberados en datos runtime o secretos
