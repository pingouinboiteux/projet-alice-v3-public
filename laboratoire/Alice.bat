@echo off
cd /d "%~dp0"
if not exist ".venv_memory\Scripts\pythonw.exe" (
    echo Installation du laboratoire incomplete.
    pause
    exit /b 1
)
start "" ".venv_memory\Scripts\pythonw.exe" -B "scripts\alice_desktop.py" --twitch
