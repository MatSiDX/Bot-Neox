# Fase 12 - Migracion Progresiva JSON -> SQLite (Bloque 1)

## Alcance de esta fase

Solo se migra el primer bloque critico y de bajo riesgo:

- `data/config.json`
- `data/permissions.json`

No se migran todavia:

- plantillas
- auditoria
- tickets
- reportes
- runtime de avas/pings
- sesiones

## Clasificacion de JSON actual

### Configuracion estable

- `data/config.json`
- `data/permissions.json`
- `data/ping_templates.json`
- `data/audit_config.json`
- `data/ticket_panels.json`

### Runtime activo

- `data/active_avalonian_pings.json`
- `data/report_runtime.json`
- `data/ticket_records.json`

### Cache

- `data/report_dashboard_requests.json` (legacy ya reemplazado por SQLite en fase 11, pero puede seguir existiendo como artefacto viejo)

### Sesiones

- `data/dashboard_sessions.json`

### Auditoria / historico

- `data/audit_events.json`
- `data/reports.json`
- `data/avalonian_interactions.json`

### Legacy / backup

- cualquier JSON historico ya reemplazado por SQLite pero conservado como respaldo temporal

## Decision de fase

Se eligio migrar primero configuracion y permisos porque:

- tienen esquema pequeno y estable
- son faciles de reconstruir
- no dependen de runtime efimero
- afectan bot y dashboard, por lo que moverlos a SQLite reduce dispersion de persistencia sin tocar UX

## Tablas nuevas

- `guild_config`
- `role_permissions`

## Estrategia aplicada

- migracion idempotente al inicializar cada repositorio
- lectura primaria desde SQLite
- fallback temporal a JSON legado si la tabla esta vacia para ese bloque
- dual-write temporal: los cambios nuevos se escriben en SQLite y tambien en el JSON legado

## Backup recomendado antes de probar

Copiar estos archivos:

- `data/config.json`
- `data/permissions.json`
- `data/bot.sqlite3`
- `data/bot.sqlite3-wal`
- `data/bot.sqlite3-shm`

## Reversion

Si algo falla:

1. Detener bot y dashboard.
2. Restaurar `data/config.json` y `data/permissions.json` desde el backup.
3. Restaurar `data/bot.sqlite3` y sus archivos WAL/SHM si quieres revertir tambien la base.
4. Como existe dual-write temporal, el JSON legado sigue reflejando los cambios recientes y permite volver a la implementacion anterior con bajo riesgo.

## Riesgos pendientes

- `ping_templates.json` sigue fuera de SQLite.
- `audit_config.json` sigue en JSON.
- `ticket_panels.json` sigue en JSON.
- Todavia no existe un comando dedicado de “auditoria de migracion” para comparar JSON vs SQLite de forma automatica.
