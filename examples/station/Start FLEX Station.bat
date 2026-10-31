@echo off
cd /d "%~dp0..\.."
title FLEX notebook (close this window to stop the notebook)
where uv >nul 2>&1 || (echo uv not found. Install it from https://docs.astral.sh/uv/ & pause & exit /b 1)
if not defined FLEX_CONFIG set FLEX_CONFIG=%~dp0flex.toml
uv sync --quiet || (pause & exit /b 1)

netstat -ano | findstr /c:":8756 " | findstr LISTENING >nul || wscript "%~dp0Start FLEX.vbs"
timeout /t 10 /nobreak >nul

uv run --no-sync marimo run "examples\station\station.py"
if errorlevel 1 pause
