@echo off
title EconomyBot Manager
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" bot_manager.py --start
) else (
  python bot_manager.py --start
)
pause
