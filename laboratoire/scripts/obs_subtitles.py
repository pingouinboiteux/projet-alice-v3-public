"""Atomic OBS text file. Subtitle failures never interrupt speech."""
import os
import threading
from pathlib import Path


class Subtitles:
    def __init__(self, path, on_error=lambda: None):
        self.path = Path(path)
        self.on_error = on_error
        self.lock = threading.Lock()
        self.generation = 0
        self.clear()

    def _write(self, text):
        temporary = self.path.with_suffix('.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(text, encoding='utf-8')
            os.replace(temporary, self.path)
        except OSError:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass
            self.on_error()

    def show(self, text):
        with self.lock:
            self.generation += 1
            self._write(' '.join(text.split())[:4000])
            return self.generation

    def clear(self, ticket=None):
        with self.lock:
            if ticket is not None and ticket != self.generation: return
            self.generation += 1
            self._write('')
