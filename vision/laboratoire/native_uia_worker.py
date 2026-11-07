"""One owned UIA reader process per task; bounded serialized JSON protocol.

No process starts at import. Failure closes the worker; no automatic retries.
"""
import json
from pathlib import Path
import queue
import subprocess
import threading


class UIAWorker:
    def __init__(self, window, *, popen=subprocess.Popen, timeout=3):
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._responses = queue.Queue(maxsize=1)
        self._sequence = 0
        self.timeout = timeout
        root = Path(__file__).resolve().parents[2]
        self.process = popen(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
            '-File', 'vision/laboratoire/native_uia_snapshot.ps1',
            '-WindowHandle', str(window['hwnd']), '-ExpectedProcessId', str(window['pid']), '-Worker'],
            cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='strict', bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        try:
            while not self._closed.is_set():
                line = self.process.stdout.readline(2 * 1024**2 + 1)
                if not line:
                    value = RuntimeError('native_reader_eof')
                elif len(line) > 2 * 1024**2 or not line.endswith('\n'):
                    value = RuntimeError('native_reader_response_too_large')
                else:
                    value = json.loads(line.lstrip('\ufeff'))
                while not self._closed.is_set():
                    try:
                        self._responses.put(value, timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if isinstance(value, Exception):
                    return
        except Exception:
            try: self._responses.put_nowait(RuntimeError('native_reader_protocol_error'))
            except queue.Full: pass

    def request(self, op, *, x=None, y=None):
        if op not in ('read', 'hit_test'):
            raise ValueError('native_reader_invalid_operation')
        if op == 'hit_test' and any(type(v) is not int or not -(2**31) <= v < 2**31 for v in (x,y)):
            raise ValueError('native_reader_invalid_point')
        with self._lock:
            if self._closed.is_set() or self.process.poll() is not None:
                raise RuntimeError('native_reader_closed')
            self._sequence += 1
            request = {'id': self._sequence, 'op': op}
            if op == 'hit_test': request.update(x=x, y=y)
            try:
                self.process.stdin.write(json.dumps(request, ensure_ascii=True) + '\n')
                self.process.stdin.flush()
                response = self._responses.get(timeout=self.timeout)
                if isinstance(response, Exception): raise response
                if (type(response) is not dict or type(response.get('id')) is not int
                        or response['id'] != self._sequence or response.get('ok') is not True
                        or type(response.get('data')) is not dict):
                    raise RuntimeError('native_reader_invalid_response')
                return response['data']
            except BaseException:
                self.close()
                raise

    def close(self):
        # Can interrupt a blocked request without acquiring its serialization lock.
        self._closed.set()
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            try: stream.close()
            except (OSError, ValueError): pass

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
