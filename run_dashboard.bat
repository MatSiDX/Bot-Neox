@echo off
title EconomyBot Dashboard
cd /d "%~dp0"
python web_dashboard.py --host 127.0.0.1 --port 8000
pause
