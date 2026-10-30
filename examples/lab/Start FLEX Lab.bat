@echo off
cd /d "%~dp0..\.."
title FLEX Lab (close this window to stop the notebook)
where uv >nul 2>&1 || (echo uv not found. Install it from https://docs.astral.sh/uv/ & pause & exit /b 1)
uv run marimo run "examples\lab\lab_test.py"
if errorlevel 1 pause
