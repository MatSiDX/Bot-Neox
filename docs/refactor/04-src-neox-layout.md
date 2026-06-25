# Fase 3 - Base `src/neox`

Fecha de actualizacion: 2026-06-18

## Objetivo

Crear la estructura base `src/neox` sin mover todo el proyecto de golpe ni romper imports actuales.

## Estructura creada

```text
src/
  __init__.py
  neox/
    __init__.py
    config/
      __init__.py
      settings.py
    core/
      __init__.py
      domain/
        __init__.py
      repositories/
        __init__.py
      services/
        __init__.py
    bot/
      __init__.py
      bootstrap.py
    dashboard/
      __init__.py
```

## Que se movio en esta fase

- La implementacion real de configuracion ahora vive en `src/neox/config/settings.py`.
- `config/settings.py` queda como wrapper de compatibilidad para no romper imports existentes.

## Wrappers temporales

- `config/settings.py`: reexporta desde `src.neox.config.settings`.
- `src/neox/bot/bootstrap.py`: expone `ProjectBot` y `build_bot` del runtime actual.

Nota posterior:

- El wrapper `src/neox/dashboard/entrypoints.py` fue retirado en Fase 14 al confirmarse que no tenia referencias vivas.

## Que NO se movio todavia

- No se movieron `cogs/`.
- No se movieron `services/`.
- No se movieron `repositories/`.
- No se movio `web_dashboard.py`.
- No se movieron entrypoints actuales como `bot.py` o `run.bat`.

## Regla de migracion progresiva

Las siguientes fases deben preferir este orden:

1. Mover modulos nuevos a `src/neox/...`.
2. Cuando un modulo legacy se migre, dejar un wrapper pequeno en la ruta vieja si todavia hay imports activos.
3. Eliminar wrappers solo cuando el arbol completo ya no dependa de ellos.

## Criterio de compatibilidad

- Los imports actuales `from config.settings import ...` siguen funcionando.
- El punto de entrada del bot sigue siendo `bot.py`.
- El punto de entrada del dashboard sigue siendo `web_dashboard.py`.
- No se altero comportamiento funcional ni persistencia.
