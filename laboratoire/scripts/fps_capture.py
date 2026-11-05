"""Runtime FPS protection; retained implementation, no training driver."""
import subprocess

def stop_capture(process, session_name):
    if not session_name.startswith(("AliceProgressive", "AliceValidationLoL")):
        raise ValueError("Refuse to stop a session outside this validation")
    command = [
        "runtime/presentmon/PresentMon-2.5.1-x64.exe",
        "--session_name",
        session_name,
        "--terminate_existing_session",
    ]
    result = subprocess.run(command, capture_output=True, timeout=15, check=False)
    if process.poll() is None:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
            subprocess.run(command, capture_output=True, timeout=15, check=False)
    query = subprocess.run(
        ["logman", "query", "-ets"],
        capture_output=True,
        timeout=10,
        check=True,
    )
    if any(
        line.split() and line.split()[0] == session_name.encode("ascii")
        for line in query.stdout.splitlines()
    ):
        raise RuntimeError("Owned ETW session survived cleanup")
    return {
        "stop_exit_code": result.returncode,
        "consumer_exited": process.poll() is not None,
        "session_absent": True,
    }
