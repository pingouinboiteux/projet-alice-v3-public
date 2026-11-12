@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0lancer.ps1" -Mode alice
if errorlevel 1 pause
