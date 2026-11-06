"""Strict, isolated LoL guard for vision validation; never starts model load.

start() returns only after a five-second valid baseline, or raises. The caller
must check() immediately before starting load and register all owned processes
in its stop callback. No desktop capture or focus manipulation occurs here.
"""
from __future__ import annotations

import json
import ctypes
from ctypes import wintypes
import math
from pathlib import Path
import subprocess
import threading
import time
import uuid
import re

from fps_frames import Frames
from game_focus import GameFocus

ROOT = Path(__file__).resolve().parents[1]


class OwnedTraceFlusher:
    """Flush only our UUID-named ETW session, never change session settings.

    API contract: learn.microsoft.com/windows/win32/api/evntrace/nf-evntrace-controltracew
    FlushTimer has a one-second minimum; explicit FLUSH avoids that delivery delay.
    """
    def __init__(self, session):
        if not re.fullmatch(r'AliceValidationLoL[0-9a-f]{16}', session):
            raise ValueError('Not an owned vision validation session name')
        self.session = session
        class Wnode(ctypes.Structure):
            _fields_ = [('BufferSize', wintypes.ULONG), ('ProviderId', wintypes.ULONG),
                        ('HistoricalContext', ctypes.c_ulonglong), ('TimeStamp', ctypes.c_ulonglong),
                        ('Guid', ctypes.c_byte * 16), ('ClientContext', wintypes.ULONG),
                        ('Flags', wintypes.ULONG)]
        class Properties(ctypes.Structure):
            _fields_ = [('Wnode', Wnode)] + [(name, wintypes.ULONG) for name in
                        ('BufferSize', 'MinimumBuffers', 'MaximumBuffers', 'MaximumFileSize',
                         'LogFileMode', 'FlushTimer', 'EnableFlags', 'AgeLimit', 'NumberOfBuffers',
                         'FreeBuffers', 'EventsLost', 'BuffersWritten', 'LogBuffersLost',
                         'RealTimeBuffersLost')] + [('LoggerThreadId', wintypes.HANDLE),
                        ('LogFileNameOffset', wintypes.ULONG), ('LoggerNameOffset', wintypes.ULONG)]
        self.buffer = ctypes.create_string_buffer(ctypes.sizeof(Properties) + 4096)
        self.properties = Properties.from_buffer(self.buffer)
        self.properties.Wnode.BufferSize = len(self.buffer)
        self.properties.LoggerNameOffset = ctypes.sizeof(Properties)
        self.properties.LogFileNameOffset = ctypes.sizeof(Properties) + 2048
        self.control = ctypes.WinDLL('advapi32', use_last_error=True).ControlTraceW
        self.control.argtypes = [ctypes.c_ulonglong, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.ULONG]
        self.control.restype = wintypes.ULONG
        self.queries = self.flushes = 0
        self.maximum_ms = 0.0
        self.lock = threading.Lock()

    def query(self):
        code = self.control(0, self.session, ctypes.byref(self.buffer), 0)
        self.queries += 1
        return code

    def flush(self):
        with self.lock:
            self._flush_locked()

    def _flush_locked(self):
        started = time.perf_counter()
        code = self.control(0, self.session, ctypes.byref(self.buffer), 3)
        self.maximum_ms = max(self.maximum_ms, (time.perf_counter() - started) * 1000)
        self.flushes += 1
        if code:
            raise OSError(code, 'Owned ETW session flush failed')
        if self.properties.EventsLost or self.properties.RealTimeBuffersLost:
            raise RuntimeError('ETW events/buffers lost; FPS instrument invalid')

    def stats(self):
        return {'calls': self.flushes, 'max_call_ms': self.maximum_ms,
                'events_lost': self.properties.EventsLost,
                'realtime_buffers_lost': self.properties.RealTimeBuffersLost}


def decision(source, displayed, source_stale, display_stale, free_ram,
             *, baseline=None, alive=True, foreground=True, instrument_ok=True):
    if not instrument_ok:
        return 'instrument_failed'
    if not alive:
        return 'game_exited'
    if not foreground:
        return 'game_not_foreground'
    if not math.isfinite(free_ram) or free_ram < 6 * 1024 ** 3:
        return 'ram_below_6gib'
    for label, metrics, stale in [('source', source, source_stale),
                                  ('display', displayed, display_stale)]:
        if not math.isfinite(stale) or stale > 1:
            return label + '_stale'
        if metrics.get('frames', 0) < 60:
            return label + '_insufficient_frames'
        fps, p95 = metrics.get('average_fps'), metrics.get('p95_ms')
        if not isinstance(fps, (int, float)) or not math.isfinite(fps):
            return label + '_invalid_fps'
        if not isinstance(p95, (int, float)) or not math.isfinite(p95) or p95 <= 0:
            return label + '_invalid_p95'
        threshold = 65 if baseline is None else 60
        if fps < threshold - (0 if baseline is None else .1):
            return label + '_below_' + str(threshold) + 'fps'
        if baseline is not None and p95 > max(1000 / 60, baseline[label]['p95_ms'] * 1.5):
            return label + '_p95_degraded'
    return None


class VisionFPSGuard:
    def __init__(self, stop_owned_callback, report_path, *, require_focus=True):
        self.stop_owned = stop_owned_callback
        self.report_path = Path(report_path)
        allowed = ROOT / 'data' / 'validation'
        if not self.report_path.resolve().is_relative_to(allowed.resolve()):
            raise ValueError('Guard report must stay in laboratoire/data/validation')
        self.report_path = self.report_path.with_name(
            self.report_path.stem + '_' + time.strftime('%Y%m%dT%H%M%S') + '_' +
            uuid.uuid4().hex[:8] + self.report_path.suffix)
        self.require_focus = require_focus
        self.reason = None
        self.done = threading.Event()
        self.thread = self.pm = self.focus = self.log = None
        self.baseline = None
        self.flusher = None
        self.report = {'profile': 'validation_vision_fps', 'status': 'not_started',
                       'policy': {'baseline_seconds': 5, 'baseline_min_fps': 65,
                                  'run_min_fps': 60, 'numeric_tolerance_fps': .1,
                                  'window_seconds': 2, 'max_stale_seconds': 1,
                                  'poll_seconds': .1, 'minimum_ram_gib': 6},
                       'samples': [], 'baseline_rows': []}
        self.executable = ROOT / 'runtime/presentmon/PresentMon-2.5.1-x64.exe'
        self.session = 'AliceValidationLoL' + uuid.uuid4().hex[:16]

    def _save(self):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(self.report, indent=2), encoding='utf-8')

    def _trip(self, reason):
        if self.reason is not None:
            return
        self.reason = reason
        self.report.update(status='stopped', stop_reason=reason)
        # Stop load before report I/O, including when the disk itself failed.
        try:
            self.stop_owned()
        except Exception as exc:
            self.report['stop_callback_error'] = repr(exc)
        try:
            self._save()
        except OSError as exc:
            self.report['report_error'] = repr(exc)

    def _observe(self):
        if self.flusher:
            self.flusher.flush()
            self.report['etw_flush'] = self.flusher.stats()
        source, stale, rows = self.frames.metrics(2)
        displayed, display_stale = self.frames.display_metrics(2)
        alive = self.game.is_running() and self.game.create_time() == self.created
        focus = self.focus.state()['foreground'] if self.focus else True
        ram = self.psutil.virtual_memory().available
        ok = not self.frames.error and self.pm.poll() is None
        reason = decision(source, displayed, stale, display_stale, ram,
                          baseline=self.baseline, alive=alive, foreground=focus,
                          instrument_ok=ok)
        if len(rows) >= 2 and abs(sum(r[1] for r in rows[1:]) - (rows[-1][2] - rows[0][2])) >= 50:
            reason = 'source_timestamp_discontinuity'
        sample = {'elapsed_s': time.monotonic() - self.started, 'source': source,
                  'display': displayed, 'source_stale_s': stale,
                  'display_stale_s': display_stale, 'free_ram_bytes': ram,
                  'foreground': focus, 'reason': reason}
        return reason, sample

    def start(self):
        if self.thread or self.pm:
            raise RuntimeError('Guard already started')
        import psutil
        self.psutil = psutil
        if not self.executable.is_file():
            raise FileNotFoundError(self.executable)
        games = []
        desktop_visible = False
        for process in psutil.process_iter(['name']):
            if (process.info['name'] or '').lower() == 'explorer.exe':
                desktop_visible = True
            if (process.info['name'] or '').lower() == 'league of legends.exe':
                games.append(process)
        if not desktop_visible:
            raise RuntimeError('Process instrument cannot see explorer.exe; game presence unknown, load forbidden')
        if len(games) != 1:
            raise RuntimeError('Exactly one running League of Legends game is required; load forbidden')
        self.game = games[0]
        self.created = self.game.create_time()
        self.report['game_pid'] = self.game.pid
        self.report['session'] = self.session
        self.started = time.monotonic()
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            self.log = self.report_path.with_suffix('.log').open('w', encoding='utf-8')
            self.pm = subprocess.Popen(
                [str(self.executable), '--process_id', str(self.game.pid),
                 '--output_stdout', '--no_console_stats', '--no_track_input',
                 '--no_track_gpu', '--session_name', self.session],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=self.log, text=True,
                encoding='utf-8-sig', creationflags=subprocess.CREATE_NO_WINDOW)
            self.frames = Frames(self.pm.stdout, self.game.pid)
            self.flusher = OwnedTraceFlusher(self.session)
            trace_deadline = time.monotonic() + 3
            while True:
                code = self.flusher.query()
                if code == 0:
                    break
                if code != 4201 or time.monotonic() >= trace_deadline:
                    raise OSError(code, 'Owned ETW session unavailable')
                time.sleep(.05)
            if self.require_focus:
                self.focus = GameFocus(self.game.pid)
                self.focus.start()
            deadline = time.monotonic() + 30
            valid_since = None
            while time.monotonic() < deadline:
                reason, sample = self._observe()
                self.report['last_baseline_observation'] = sample
                self.report['baseline_rows'].append(sample)
                self.report['baseline_rows'] = self.report['baseline_rows'][-300:]
                self.report['capture_instrument'] = {
                    'error': self.frames.error,
                    'exit_code': self.pm.poll(),
                    'selected_swapchain': self.frames.chain,
                    'seen_swapchains': dict(self.frames.chains),
                }
                now = time.monotonic()
                if reason is None:
                    valid_since = now if valid_since is None else valid_since
                    if now - valid_since >= 5:
                        self.baseline = {'source': sample['source'], 'display': sample['display']}
                        break
                else:
                    valid_since = None
                    if reason in ('instrument_failed', 'game_exited', 'ram_below_6gib'):
                        raise RuntimeError('Baseline refused: ' + reason)
                if self.done.wait(.1):
                    raise RuntimeError('Guard closed during baseline')
            if self.baseline is None:
                raise RuntimeError('No five-second valid >=65 FPS baseline within 30 seconds')
            self.report.update(status='monitoring', baseline=self.baseline)
            self.report['samples'].append(sample)
            self._save()
            self.thread = threading.Thread(target=self._monitor, daemon=True)
            self.thread.start()
            self.check()
            return self
        except Exception as exc:
            self._trip('startup_failed: ' + repr(exc))
            self.close()
            raise

    def _monitor(self):
        last_saved = time.monotonic()
        while not self.done.wait(.1):
            try:
                reason, sample = self._observe()
                if reason:
                    self.report['stop_observation'] = sample
                    self._trip(reason)
                    return
                if time.monotonic() - last_saved >= 1:
                    self.report['samples'].append(sample)
                    self.report['samples'] = self.report['samples'][-1800:]
                    self._save()
                    last_saved = time.monotonic()
            except Exception as exc:
                self._trip('monitor_failed: ' + repr(exc))
                return

    def check(self):
        if self.reason:
            raise RuntimeError('Vision load stopped: ' + self.reason)
        if self.baseline is None or self.done.is_set():
            raise RuntimeError('Vision guard not active; load forbidden')
        try:
            reason, sample = self._observe()
        except Exception as exc:
            self._trip('check_failed: ' + repr(exc))
            raise RuntimeError('Vision guard observation failed; load stopped') from exc
        if reason:
            self.report['stop_observation'] = sample
            self._trip(reason)
            raise RuntimeError('Vision load stopped: ' + reason)

    def close(self):
        self.done.set()
        cleanup_errors = []
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                cleanup_errors.append('Monitor did not stop within three seconds')
        if self.focus:
            try:
                self.focus.close()
            except Exception as exc:
                cleanup_errors.append(repr(exc))
            self.focus = None
        try:
            if self.pm:
                # Same owned-session protocol as fps_capture.stop_capture, with
                # explicit executable/cwd so caller working directory is irrelevant.
                try:
                    subprocess.run([str(self.executable), '--session_name', self.session,
                                    '--terminate_existing_session'], cwd=ROOT,
                                   capture_output=True, timeout=15, check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                finally:
                    try:
                        self.pm.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.pm.kill()
                        self.pm.wait(timeout=5)
                sessions = subprocess.run(['logman', 'query', '-ets'], capture_output=True,
                                          timeout=10, check=True,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
                if any(line.split() and line.split()[0] == self.session.encode('ascii')
                       for line in sessions.stdout.splitlines()):
                    raise RuntimeError('Owned PresentMon session survived cleanup')
                self.report['capture_cleanup'] = 'consumer exited and owned session absent'
                self.pm.stdout.close()
                self.pm = None
        except Exception as exc:
            cleanup_errors.append(repr(exc))
        finally:
            if self.log:
                self.log.close()
                self.log = None
            if not self.reason:
                self.report['status'] = 'closed'
            if cleanup_errors:
                self.report.update(status='cleanup_failed', cleanup_errors=cleanup_errors)
            self._save()
        if cleanup_errors:
            raise RuntimeError('Guard cleanup incomplete: ' + '; '.join(cleanup_errors))
