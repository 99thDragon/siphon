@echo off
title SIPHON
cd /d "%~dp0"
python server.py
echo.
echo SIPHON has stopped. Press any key to close this window.
pause >nul
