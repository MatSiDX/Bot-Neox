@echo off
title EconomyBot Dashboard
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" web_dashboard.py --host 127.0.0.1 --port 8000
) else (
  python web_dashboard.py --host 127.0.0.1 --port 8000
)
pause
