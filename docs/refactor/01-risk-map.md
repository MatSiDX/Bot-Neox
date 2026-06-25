# Fase 0 - Risk Map

Fecha de revision: 2026-06-18

## Principio de trabajo

El refactor debe ser progresivo, reversible y sin cambio funcional. Los riesgos se priorizan por acoplamiento, superficie de efectos secundarios y baja cobertura automatizada.

## Riesgos principales

| Area | Riesgo | Motivo | Impacto si se toca sin baseline |
| --- | --- | --- | --- |
| `web_dashboard.py` | Alto | Modulo monolitico con mezcla de routing, HTML, sesiones, permisos, acceso a datos y utilidades | Regresiones amplias en dashboard, auth o lectura de datos |
| `config/settings.py` + `load_dotenv()` | Medio | Configuracion compartida por multiples entry points | Cambios pequenos pueden alterar arranque de bots y dashboard |
| `repositories/database.py` | Alto | Inicializa tablas e incluye compatibilidad evolutiva de esquema | Riesgo de tocar SQLite o datos runtime accidentalmente |
| `data/` | Alto | Contiene base, JSON operativos, sesiones, logs y evidencias | Riesgo de contaminar baseline o exponer informacion sensible |
| Multiples entry points (`bot.py`, `bot_manager.py`) | Bajo/Medio | El bot tiene mas de una forma de arranque local aunque ya existe una sola instancia oficial | Cambios apresurados pueden desalinear experiencia de arranque |
| Cobertura automatizada actual | Medio | Hay tests utiles, pero concentrados en tickets, Albion y vistas/reportes | Parte importante del dashboard y del flujo de arranque no tiene red de seguridad fuerte |

## Riesgos secundarios

| Area | Riesgo | Observacion |
| --- | --- | --- |
| Import side effects | Medio | Algunos modulos cargan configuracion o rutas al importar |
| Persistencia mixta SQLite + JSON | Medio | La verdad del sistema depende de mas de un backend |
| Scripts operativos en `scripts/` | Bajo/Medio | Pueden confundirse con scripts seguros si no se documentan bien |
| Bot secundario | Medio | Debe conservarse aunque aun no se reorganice |

## Zonas seguras para Fase 1

Cambios razonablemente seguros si se mantienen sin comportamiento nuevo:

- Documentacion adicional del arbol y dependencias.
- Extraccion de constantes o helpers puramente internos si quedan cubiertos por baseline.
- Agrupacion de comandos de validacion y verificacion.
- Aislamiento de imports utilitarios sin tocar rutas HTTP, slash commands ni persistencia.

## Zonas no seguras para iniciar

Evitar como primer movimiento estructural:

- Reescritura o troceado grande de `web_dashboard.py`.
- Cambios en `repositories/database.py` o tablas SQLite.
- Cambios de formato en archivos JSON de `data/`.
- Cambios en nombres, firma o registro de slash commands.
- Eliminacion de entry points legacy.

## Reglas de seguridad para las siguientes fases

- Mantener `python -m compileall .` en verde antes y despues de cada bloque de cambios.
- Ejecutar `python -m unittest discover -s tests -v` siempre que las dependencias esten instaladas.
- No usar `run.bat`, `bot.py` ni `web_dashboard.py` como validacion de refactor.
- No editar archivos runtime dentro de `data/` para "acomodar" pruebas.
- Si un cambio afecta arranque, permisos, sesiones o persistencia, hacerlo en pasos pequenos y con diff facil de revertir.

## Pendientes tecnicos detectados para Fase 1

- Delimitar seams internos del dashboard sin mover comportamiento todavia.
- Inventariar imports compartidos entre `cogs/`, `services/`, `repositories/` y `web_dashboard.py`.
- Definir una estrategia de pruebas de humo por modulo que no requiera Discord ni login real.
