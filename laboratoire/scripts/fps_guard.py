"""Runtime FPS protection; retained implementation, no training driver."""
import json
import subprocess
import threading
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from fps_snapshot import snapshot
from fps_capture import stop_capture
from fps_policy import stop_reason
from fps_frames import Frames

class NativeGuard:
    def __init__(
        self,
        supervisor,
        label,
        *,
        duration_seconds=600,
        minimum_fps=120,
        focus_aware=False,
        baseline_seconds=25,
        exercise_stop_control=True,
    ):
        self.supervisor = supervisor
        self.label = label
        assert 60 <= duration_seconds <= 1800
        self.duration_seconds = duration_seconds
        assert minimum_fps in (60, 90, 120)
        self.minimum_fps = minimum_fps
        self.focus_aware = focus_aware
        self.window_seconds = 3 if minimum_fps == 60 else 1.5
        self.settling_seconds = 3.5 if minimum_fps == 60 else 2
        self.focus = None
        assert 2 <= baseline_seconds <= 25
        self.baseline_seconds = baseline_seconds
        self.exercise_stop_control = exercise_stop_control
        self.done = threading.Event()
        self.ready = threading.Event()
        self.reason = None
        self._fps_dip_since = None
        self.thread = None
        self.pm = None
        self.log = None
        self.files = ExitStack()
        self.report = {
            "label": label,
            "status": "baseline",
            "samples": [],
            "optimizer_steps": 0,
        }
        self.path = Path(f"data/runtime/fps_guard_{label}.json")
        self.report["fps_policy"] = {
            "minimum_fps": minimum_fps,
            "focus_aware": focus_aware,
            "window_seconds": self.window_seconds if focus_aware else 5,
            "return_settling_seconds": self.settling_seconds if focus_aware else 0,
            "stop_floor_fps": 55 if minimum_fps == 60 else minimum_fps,
            "brief_dip_grace_seconds": 6 if minimum_fps == 60 else 0,
            "immediate_stop_floor_fps": 45 if minimum_fps == 60 else minimum_fps,
        }

    def filter_brief_fps_dip(self, reason, now, metrics, displayed):
        # Proprietaire permits brief game stutters during the 60 FPS tests. This
        # delay applies only to a moderate FPS dip, never RAM or lost evidence.
        if self.minimum_fps != 60 or reason != "average_below_55fps":
            self._fps_dip_since = None
            return reason
        if min(metrics['average_fps'], displayed['average_fps']) < 45:
            return reason
        if self._fps_dip_since is None:
            self._fps_dip_since = now
        return reason if now - self._fps_dip_since >= 6 else None

    def decide(self, metrics, reference, stale, free_ram):
        return stop_reason(
            metrics,
            reference,
            stale_seconds=stale,
            free_ram_bytes=free_ram,
            minimum_fps=self.minimum_fps,
            check_tails=not self.focus_aware,
        )

    def save(self):
        self.path.write_text(json.dumps(self.report, indent=2) + "\n")

    def stop_owned(self):
        # Do not pop the entry: Supervisor.start may be polling this same process.
        process = self.supervisor.processes.get("language_model")
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def start(self):
        current = snapshot()
        games = current["games"]
        assert len(games) == 1 and len(current["games"]) == 1
        self.pid = games[0]["Id"]
        if self.focus_aware:
            from game_focus import GameFocus

            self.focus = GameFocus(self.pid)
            self.focus.start()
        self.report["game_pid"] = self.pid
        self.session = "AliceProgressiveNative" + datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        self.log = self.files.enter_context(
            Path(  # noqa: SIM115 - this handle is owned by the instance ExitStack
                f"data/runtime/fps_guard_{self.label}.log"
            ).open("w")
        )
        self.pm = subprocess.Popen(
            [
                "runtime/presentmon/PresentMon-2.5.1-x64.exe",
                "--process_id",
                str(self.pid),
                "--output_stdout",
                "--no_console_stats",
                "--no_track_input",
                # This guard measures presents and displayed frames, not GPU work durations.
                # Keep display tracking; avoid unrelated GPU-event correlation latency.
                "--no_track_gpu",
                "--session_name",
                self.session,
                "--timed",
                str(self.duration_seconds),
                "--terminate_after_timed",
            ],
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            encoding="utf-8-sig",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.frames = Frames(self.pm.stdout, self.pid)
        print(
            f"Frame guard: measuring {self.baseline_seconds} foreground seconds",
            flush=True,
        )
        if self.focus is not None:
            deadline = time.monotonic() + 240
            while self.focus.state()["foreground_seconds"] < self.baseline_seconds:
                assert time.monotonic() < deadline, "No stable foreground game baseline"
                time.sleep(0.25)
            self.report["foreground_baseline_verified"] = True
        else:
            time.sleep(self.baseline_seconds)
        current = snapshot()
        self.reference, stale, rows = self.frames.metrics(
            min(20, self.baseline_seconds)
        )
        self.display_reference, display_stale = self.frames.display_metrics(
            min(20, self.baseline_seconds)
        )
        assert (
            len(rows) >= 100
            and abs(sum(r[1] for r in rows[1:]) - (rows[-1][2] - rows[0][2])) < 50
        )
        assert not self.frames.error and self.pm.poll() is None
        self.report["reference"] = self.reference
        self.report["display_reference"] = self.display_reference
        self.reason = self.decide(
            self.reference, self.reference, stale, current["windows_free_ram_bytes"]
        ) or self.decide(
            self.display_reference, self.display_reference, display_stale,
            current["windows_free_ram_bytes"],
        )
        if self.reason:
            self.report.update(status="baseline_refused", stop_reason=self.reason)
            self.save()
            raise RuntimeError(f"Game baseline refused: {self.reason}")
        # Exercise the exact native stop callback before any GPU service is launched.
        if self.exercise_stop_control:
            dummy = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Start-Sleep -Seconds 30",
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.supervisor.processes["language_model"] = dummy
            time.sleep(1)
            self.stop_owned()
            assert dummy.poll() is not None
            self.supervisor.processes.pop("language_model")
            self.report["native_stop_control_exited"] = True
        else:
            assert self.report.get("stop_control_provenance"), (
                "Missing prior stop control"
            )
            self.report["stop_control_reused"] = True
        self.report["status"] = "monitoring"
        self.save()
        self.thread = threading.Thread(target=self.monitor, daemon=True)
        self.thread.start()
        assert self.ready.wait(timeout=20), "No initial live guard observation"
        self.check()

    def monitor(self):
        current, last_snapshot = None, 0
        while not self.done.wait(0.5):
            try:
                now = time.monotonic()
                focus_state = self.focus.state() if self.focus is not None else None
                seconds = (
                    min(self.window_seconds, max(0.01, focus_state["foreground_seconds"] - 0.5))
                    if focus_state
                    else 5
                )
                metrics, stale, _ = self.frames.metrics(seconds)
                displayed, display_stale = self.frames.display_metrics(seconds)
                if now - last_snapshot > 5:
                    current = snapshot()
                    last_snapshot = now
                    self.report["samples"].append(
                        {
                            "utc": datetime.now(UTC).isoformat(),
                            "frames": metrics,
                            "display_frames": displayed,
                            "windows_free_ram_bytes": current["windows_free_ram_bytes"],
                            "game_focus": focus_state,
                        }
                    )
                    self.save()
                if focus_state is None or (
                    focus_state["foreground"] and focus_state["foreground_seconds"] >= self.settling_seconds
                ):
                    source_reason = self.decide(
                        metrics,
                        self.reference,
                        stale,
                        current["windows_free_ram_bytes"],
                    )
                    display_reason = self.decide(
                        displayed,
                        self.display_reference,
                        display_stale,
                        current["windows_free_ram_bytes"],
                    )
                    # A delayed FPS warning must never hide stale display
                    # measurements or another immediately actionable failure.
                    reasons = (source_reason, display_reason)
                    reason = next((r for r in reasons if r and r != "average_below_55fps"), None)
                    reason = reason or source_reason or display_reason
                else:
                    reason = (
                        "windows_ram_headroom"
                        if current["windows_free_ram_bytes"] < 6 * 1024**3
                        else None
                    )
                reason = self.filter_brief_fps_dip(reason, now, metrics, displayed)
                if self.frames.error or self.pm.poll() is not None:
                    reason = "frame_instrument_failed"
                if [p["Id"] for p in current["games"]] != [self.pid]:
                    reason = "game_exited_or_changed"
                if reason and not self.reason:
                    self.report["stop_observation"] = {
                        "utc": datetime.now(UTC).isoformat(),
                        "frames": metrics,
                        "display_frames": displayed,
                        "source_stale_seconds": stale,
                        "display_stale_seconds": display_stale,
                        "windows_free_ram_bytes": current["windows_free_ram_bytes"],
                        "selected_swapchain": self.frames.chain,
                        "seen_swapchains": dict(self.frames.chains),
                        "last_any_frame": self.frames.last_any,
                    }
                self.reason = self.reason or reason
            except Exception as exc:  # noqa: BLE001 - any monitoring failure must stop load
                self.reason = self.reason or repr(exc)
            self.ready.set()
            if self.reason:
                self.report["stop_reason"] = self.reason
                self.report["status"] = "stopped_by_guard"
                self.save()
                self.stop_owned()

    def check(self):
        if self.reason:
            raise RuntimeError(f"Native inference stopped by live guard: {self.reason}")

    def close(self):
        self.done.set()
        if self.thread is not None:
            self.thread.join(timeout=20)
            assert not self.thread.is_alive()
        try:
            try:
                if self.focus is not None:
                    self.focus.close()
                    if self.focus.error is None:
                        self.report["final_game_focus"] = self.focus.state()
                    else:
                        self.report["focus_instrument_error"] = self.focus.error
            finally:
                if self.pm is not None:
                    self.report["capture_cleanup"] = stop_capture(self.pm, self.session)
        finally:
            self.files.close()
        if not self.reason and (
            self.report.get("native_stop_control_exited")
            or self.report.get("stop_control_reused")
        ):
            self.report["status"] = "passed"
        self.save()
