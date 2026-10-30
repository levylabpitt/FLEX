@echo off
cd /d "%~dp0..\.."
title FLEX Station (close this window to stop the notebook)
where uv >nul 2>&1 || (echo uv not found. Install it from https://docs.astral.sh/uv/ & pause & exit /b 1)
set FLEX_CONFIG=%~dp0flex.toml
uv sync --quiet || (pause & exit /b 1)

netstat -ano | findstr /c:":29500 " | findstr LISTENING >nul || start "flex serve" /min uv run --no-sync flex serve
timeout /t 5 /nobreak >nul

uv run --no-sync marimo run "examples\station\station.py"
if errorlevel 1 pause
