"""One-use task permission; not an interpreter of the user's yes/no answer.

Only trusted local dialogue code may approve after interpreting the complete
utterance. A model, page or remote chat must never receive these capabilities.
"""
from copy import deepcopy
import math
import threading
import time


def _task(value):
    if type(value) is not dict or set(value) != {'window', 'target', 'text'}:
        raise ValueError('native_permission_task_invalid')
    window=value['window']
    if (type(window) is not dict or set(window)!={'hwnd','pid','created'}
            or any(type(window[k]) is not int or window[k]<=0 for k in ('hwnd','pid'))
            or type(window['created']) not in (int,float) or not math.isfinite(window['created'])
            or window['created']<=0):
        raise ValueError('native_permission_window_invalid')
    if type(value['target']) is not str or not value['target']:
        raise ValueError('native_permission_target_invalid')
    text=value['text']
    if (type(text) is not str or not text.strip() or len(text)>4000
            or any(ord(c)<32 and c not in '\n\t' for c in text)):
        raise ValueError('native_permission_text_invalid')
    return deepcopy(value)


class NativeTaskPermission:
    def __init__(self, *, clock=time.monotonic, ttl=60):
        if type(ttl) not in (int,float) or not math.isfinite(ttl) or not 0<ttl<=120:
            raise ValueError('native_permission_ttl_invalid')
        self.clock,self.ttl=clock,ttl
        self._lock=threading.RLock()
        self._ticket=self._permit=self._lease=self._task=None
        self._deadline=self._last=None

    def cancel(self):
        with self._lock:
            self._ticket=self._permit=self._lease=self._task=None

    @staticmethod
    def _local(source):
        if source not in ('text','voice'):
            raise ValueError('native_permission_local_source_required')

    def _now(self):
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now) or (self._last is not None and now<self._last):
            self.cancel()
            raise ValueError('native_permission_clock_invalid')
        self._last=now
        return now

    def _pending(self):
        now=self._now()
        if self._task is None or now>=self._deadline:
            self.cancel()
            raise ValueError('native_permission_missing_or_expired')

    def propose(self, task, *, source):
        self._local(source)
        with self._lock:
            # Even a malformed correction revokes the former proposal.
            self.cancel()
            validated=_task(task)
            self._deadline=self._now()+self.ttl
            self._task=validated
            self._ticket=object()
            return {'ticket':self._ticket,'task':deepcopy(validated),'expires_at':self._deadline}

    def approve(self, ticket, decision, *, source):
        self._local(source)
        with self._lock:
            self._pending()
            if ticket is not self._ticket or self._ticket is None:
                raise ValueError('native_permission_stale_review')
            if decision is not True:
                self.cancel()
                raise ValueError('native_permission_not_approved')
            self._ticket=None
            self._permit=object()
            return self._permit

    def claim(self, permit, task):
        with self._lock:
            self._pending()
            if permit is not self._permit or self._permit is None or _task(task)!=self._task:
                raise ValueError('native_permission_scope_mismatch')
            self._permit=None
            self._lease=object()
            return self._lease

    def active(self, lease):
        with self._lock:
            try: self._pending()
            except ValueError: return False
            return lease is self._lease and self._lease is not None

    def finish(self, lease):
        with self._lock:
            if lease is self._lease and self._lease is not None:
                self.cancel()
