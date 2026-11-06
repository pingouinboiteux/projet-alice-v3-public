"""Versioned local review, with one-use authorization and no side effects.

Only the trusted local-input boundary may supply source metadata. Never infer
it from a page or model response. claim() is the commitment boundary: cancelling
after a successful claim cannot retract an operation already dispatched by the
caller. The caller must claim immediately before its separately guarded action.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import secrets
import threading
import time


@dataclass(frozen=True)
class Authorization:
    version: int
    nonce: str


def _target(target):
    if type(target) is not dict or set(target) != {'title', 'body'}:
        raise ValueError('note_schema')
    title, body = target['title'], target['body']
    if type(title) is not str or type(body) is not str:
        raise ValueError('note_values_must_be_text')
    if not title.strip() or len(title) > 80 or any(c in title for c in '\r\n\x00') or title.startswith('$:/'):
        raise ValueError('invalid_title')
    if not body.strip() or len(body) > 4096 or '\x00' in body:
        raise ValueError('invalid_body')
    return (title, body)


class PendingNoteReview:
    def __init__(self, *, ttl_seconds=60, clock=time.monotonic):
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 60:
            raise ValueError('ttl_must_be_positive_and_at_most_60_seconds')
        if not callable(clock):
            raise TypeError('clock_required')
        self._ttl, self._clock = ttl_seconds, clock
        self._lock = threading.RLock()
        self._version = 0
        self._last_time = None
        self._values = self._source = self._deadline = None
        self._ticket = self._authorization = None

    def _invalidate(self):
        self._values = self._source = self._deadline = None
        self._ticket = self._authorization = None

    def _now(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now) or (self._last_time is not None and now < self._last_time):
            self._invalidate()
            raise ValueError('invalid_monotonic_clock')
        self._last_time = now
        return now

    def _require_pending(self):
        now = self._now()
        if self._values is None:
            raise ValueError('no_pending_note')
        if now >= self._deadline:
            self._invalidate()
            raise ValueError('pending_note_expired')
        return now

    @staticmethod
    def _source_allowed(source):
        if type(source) is not str or source not in ('local_text', 'voice'):
            raise ValueError('untrusted_input_source')

    def _replace(self, values, source):
        now = self._now()
        self._version += 1
        self._values, self._source = values, source
        self._deadline = now + self._ttl
        self._ticket = self._authorization = None
        return self._version

    def propose(self, target, source):
        self._source_allowed(source)
        values = _target(target)
        with self._lock:
            return self._replace(values, source)

    def correct(self, target, source='local_text'):
        self._source_allowed(source)
        values = _target(target)
        with self._lock:
            self._require_pending()
            return self._replace(values, source)

    def review(self):
        with self._lock:
            self._require_pending()
            self._ticket = secrets.token_urlsafe(24)
            self._authorization = None
            return {'ticket': self._ticket, 'version': self._version,
                    'target': {'title': self._values[0], 'body': self._values[1]},
                    'source': self._source, 'expires_at': self._deadline}

    def confirm(self, ticket, response, source='local_text'):
        # Voice cannot approve its own potentially mistaken transcription.
        if source != 'local_text' or type(source) is not str:
            raise ValueError('explicit_local_text_confirmation_required')
        if type(response) is not str or response not in ('oui', 'je confirme'):
            raise ValueError('explicit_confirmation_required')
        with self._lock:
            self._require_pending()
            if type(ticket) is not str or not ticket.isascii() or self._ticket is None or not secrets.compare_digest(ticket, self._ticket):
                raise ValueError('unknown_or_stale_review')
            self._ticket = None
            self._authorization = Authorization(self._version, secrets.token_urlsafe(24))
            return self._authorization

    def claim(self, authorization):
        with self._lock:
            self._require_pending()
            # Identity rejects copied or reconstructed objects, even with the
            # same public fields. Capabilities never cross a model/page boundary.
            if authorization is not self._authorization or type(authorization) is not Authorization or authorization.version != self._version:
                raise ValueError('unknown_or_stale_authorization')
            target = {'title': self._values[0], 'body': self._values[1]}
            self._invalidate()
            return target

    def authorize_request(self, ticket, *, source):
        """Local controller only, after exact-intent checks; not a pretend button click.

        Voice is allowed by the user's hands-free policy. This method does not
        classify text: the caller must check intent before issuing this capability.
        """
        self._source_allowed(source)
        with self._lock:
            self._require_pending()
            if source != self._source:
                raise ValueError('request_source_changed')
            if type(ticket) is not str or not ticket.isascii() or self._ticket is None or not secrets.compare_digest(ticket, self._ticket):
                raise ValueError('unknown_or_stale_review')
            self._ticket = None
            self._authorization = Authorization(self._version, secrets.token_urlsafe(24))
            return self._authorization

    def cancel(self):
        with self._lock:
            self._version += 1
            self._invalidate()
            return self._version
