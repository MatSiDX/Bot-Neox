# Fase 13 - Permisos Centralizados y Endurecimiento de Seguridad

## Objetivo

Unificar la validacion de permisos entre bot y dashboard, aplicar `deny-by-default` por modulo y cerrar accesos demasiado amplios en endpoints sensibles.

## Fuente unica de verdad

La definicion central de permisos queda en:

- `services/permission_service.py`

Desde ahi se exponen:

- claves publicas legacy de permisos
- etiquetas y descripciones compartidas
- reglas de acceso por modulo
- mapeo de secciones del dashboard

## Modulos cubiertos

- economia
- tickets
- multas
- auditoria
- plantillas
- Albion registration
- exportaciones
- configuracion sensible
- permisos administrativos del bot

## Compatibilidades mantenidas

- `economia` sigue habilitando operaciones y exportacion de economia
- `tickets` sigue habilitando gestion de tickets y media asociada
- `plantillas` sigue habilitando gestion de plantillas
- `informes` sigue cubriendo revision de informes y registro Albion
- `permisos` sigue cubriendo administracion de permisos y configuraciones sensibles
- `global` sigue actuando como acceso total

Compatibilidad temporal adicional:

- `multas` acepta `tickets` o `informes` para no romper flujos existentes mientras se refina el modelo

## Endpoints endurecidos

- `/ticket-transcript` ahora requiere permiso de tickets
- `/ticket-media/*` ahora valida el `guild_id` embebido en la ruta y requiere permiso de tickets
- `/api/ticket-live` ahora requiere permiso de tickets
- `/api/ticket-live-message` ahora exige CSRF y permiso de tickets
- `/api/economy/*` ahora usa permiso de economia
- `/api/ping-templates` ahora usa permiso de plantillas
- `/api/audit-config` y `/api/audit-events` ahora usan permiso de auditoria
- `/api/albion-registration` ahora usa permiso de informes/Albion
- `/api/bot-permissions` ahora usa permiso administrativo del bot
- `/api/export/*` ya no comparte una validacion generica: cada exportacion exige el permiso correcto

## Auditoria administrativa

Los siguientes cambios del dashboard generan evento en `audit_events.json`:

- configuracion de multas
- configuracion de auditoria
- configuracion Albion registration
- permisos del bot
- guardado y eliminacion de plantillas
- cambios y publicacion de paneles de tickets

## Errores internos

El dashboard ya no devuelve errores crudos al cliente en los endpoints tocados por esta fase. Los detalles quedan solo en consola mediante logging seguro.

## Pendiente para fases futuras

- separar permisos legacy del bot de permisos estrictos del dashboard si se quiere granularidad aun mayor
- migrar auditoria JSON a persistencia mas estructurada
- ampliar pruebas de integracion del dashboard cuando el entorno tenga `discord.py` y `aiohttp`
