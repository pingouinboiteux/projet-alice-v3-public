"""Short-lived public scene, with explicit provenance and no persistence.

Only admitted Twitch messages, delivered public Alice replies and deliberately
shared local directives belong here. Ordinary local dialogue is never accepted
implicitly. The caller owns delivery checks and the local-command boundary.
"""
from collections import deque
import math
import re
import threading
import time

from remote_dialogue import RemoteText

MAX_EVENTS = 12
MAX_CHARACTERS = 6000
MAX_TEXT = 2000
TTL_SECONDS = 300


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError('Texte public invalide')
    return value.strip()


def parse_scene_command(text):
    """Return an explicit /scene or 'pour le stream, ...' local directive.

    Invoke on local input only. A viewer quoting /scene has no such authority.
    None means ordinary input; an empty or oversized command is invalid.
    """
    if not isinstance(text, str):
        raise ValueError('Commande locale invalide')
    parts = text.strip().split(maxsplit=1)
    if parts and parts[0] == '/scene':
        return _text(parts[1] if len(parts) == 2 else '')
    spoken = re.fullmatch(r'(?:alice(?:\s*[:,]\s*|\s+))?pour le stream(?:\s*[:,]\s*|\s+|$)(.*)',
                          text.strip(), flags=re.IGNORECASE | re.DOTALL)
    return _text(spoken.group(1)) if spoken else None


class PublicScene:
    def __init__(self, *, clock=time.monotonic):
        if not callable(clock):
            raise TypeError('Horloge requise')
        self.clock = clock
        self._lock = threading.Lock()
        self._entries = deque()
        self._last_time = None

    def _expire(self):
        now = self.clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            self._entries.clear()
            raise ValueError('Horloge invalide')
        # A reset/test clock must not retain entries with a negative age.
        if self._last_time is not None and now < self._last_time:
            self._entries.clear()
        self._last_time = now
        while self._entries and now - self._entries[0][0] >= TTL_SECONDS:
            self._entries.popleft()
        return now

    def _record(self, event):
        with self._lock:
            now = self._expire()
            self._entries.append((now, event))
            while (len(self._entries) > MAX_EVENTS or
                   sum(sum(len(value) for value in row.values())
                       for _, row in self._entries) > MAX_CHARACTERS):
                self._entries.popleft()

    def record_viewer(self, message):
        if type(message) is not RemoteText or message.source != 'twitch':
            raise ValueError('Message Twitch authentifie par le transport requis')
        self._record({'source': 'twitch', 'author': message.author,
                      'kind': 'viewer', 'text': _text(message.text), 'recipient': 'Alice'})

    def record_alice(self, text, *, recipient=''):
        """Record only after successful public delivery, never after generation."""
        if not isinstance(recipient, str) or len(recipient) > 80:
            raise ValueError('Destinataire public invalide')
        self._record({'source': 'alice', 'author': 'Alice',
                      'kind': 'alice', 'text': _text(text), 'recipient': recipient})

    def record_directive(self, text):
        """Caller must have accepted an explicit local scene command."""
        self._record({'source': 'local', 'author': 'Proprietaire',
                      'kind': 'directive', 'text': _text(text), 'recipient': 'Alice'})

    def snapshot(self):
        with self._lock:
            self._expire()
            return [dict(event) for _, event in self._entries]

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._last_time = None
