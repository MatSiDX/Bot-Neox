# Fase 0 - Validation Checklist

## Objetivo

Validar que el proyecto siga importando, compilando y descubriendo pruebas sin conectar el bot a Discord ni modificar datos runtime.

## Reglas de seguridad

- No ejecutar `python bot.py`.
- No usar `run.bat` para validar refactor.
- No abrir conexiones manuales contra Discord.
- No editar ni borrar archivos dentro de `data/` como parte de la validacion.

## Precondiciones

- Usar el entorno virtual del proyecto si existe.
- Tener instaladas las dependencias de `requirements.txt` si se quieren correr los tests.
- Mantener `.env` local fuera del control de versiones y sin imprimir su contenido.

## Comandos seguros

Compilacion del arbol Python:

```bat
python -m compileall .
```

Descubrimiento y ejecucion de pruebas existentes:

```bat
python -m unittest discover -s tests -v
```

Wrapper local para correr ambas validaciones:

```bat
python scripts\validate_local.py
```

## Interpretacion de resultados

- `compileall` debe finalizar sin errores de sintaxis.
- `unittest discover` debe descubrir pruebas o informar claramente por que no pudo ejecutarlas.
- Si falla por `ModuleNotFoundError` o dependencia ausente, registrar el problema como bloqueo de entorno, no como cambio funcional del refactor.

## Checklist operativo

- [x] Documentar las validaciones seguras.
- [x] Mantener fuera del flujo cualquier conexion real a Discord.
- [x] Definir comando unico auxiliar para baseline local.
- [x] Ejecutar `python -m compileall .`
- [x] Ejecutar `python -m unittest discover -s tests -v`
- [x] Registrar resultados del entorno actual en el cierre de la fase

## Resultado observado en este entorno

Fecha de ejecucion: 2026-06-18

- `python -m compileall .`: OK
- `python -m unittest discover -s tests -v`: bloqueado por dependencias faltantes del entorno

Dependencias faltantes reportadas por los imports de prueba:

- `aiohttp`
- `discord` (provisto por `discord.py`)
- `dotenv` (provisto por `python-dotenv`)

Conclusion del baseline:

- No se detectaron errores de sintaxis en el arbol Python.
- La base actual de tests no pudo ejecutarse en este entorno porque faltan dependencias declaradas en `requirements.txt`.
- El bloqueo es de preparacion local, no evidencia un cambio funcional introducido por Fase 0.

## Nota para fases siguientes

Antes de cada bloque de refactor:

1. Ejecutar `python -m compileall .`.
2. Ejecutar `python -m unittest discover -s tests -v` si el entorno tiene dependencias.
3. Revisar que no haya cambios accidentales en `data/`, `.env` o logs runtime.
