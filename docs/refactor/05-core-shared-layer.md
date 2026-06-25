# Fase 4 - Core compartido inicial

Fecha de actualizacion: 2026-06-18

## Objetivo

Empezar a mover logica reusable a `src/neox/core` sin cambiar comportamiento visible ni mover todo el proyecto de golpe.

## Piezas movidas en esta fase

Servicios:

- `ConfigService`
- `PingTemplateService`

Repositorios:

- `ConfigRepository`
- `PingTemplateRepository`

Apoyo de dominio:

- `src/neox/core/domain/config_keys.py`

## Motivo de seleccion

Estas piezas son de bajo riesgo porque:

- Ya se usan tanto desde bot como desde dashboard.
- No importan `discord.py`.
- No importan componentes HTTP ni del dashboard.
- Trabajan con JSON y configuracion pura.

## Wrappers de compatibilidad

Se mantienen las rutas antiguas:

- `services/config_service.py`
- `repositories/config_repository.py`
- `services/ping_template_service.py`
- `repositories/ping_template_repository.py`

Cada una reexporta la implementacion real desde `src/neox/core/...`.

## Dependencias evitadas en `core`

La capa `core` introducida en esta fase no importa:

- `discord`
- `discord.ext`
- `BaseHTTPRequestHandler`
- `web_dashboard`

## Que queda pendiente

Todavia no se movieron:

- `FineService` porque depende de `discord.py`.
- `PermissionService` porque su API actual depende de objetos `member` del runtime de Discord.
- Servicios y repositorios de reportes, balances y Albion.
- Cogs y rutas del dashboard.

## Regla para la siguiente fase

Las proximas migraciones hacia `core` deben priorizar piezas con:

1. Dependencias puras de Python.
2. Reutilizacion entre bot y dashboard.
3. Riesgo bajo de acoplamiento a runtime de Discord.
