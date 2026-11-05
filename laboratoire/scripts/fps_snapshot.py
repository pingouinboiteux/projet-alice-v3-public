"""Runtime FPS protection; retained implementation, no training driver."""
import json
import subprocess

def snapshot():
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/mesurer_entrainement_windows.ps1",
        ],
        capture_output=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout.decode("utf-8-sig"))
