"""Single-use observed native actions. No OS input is implemented here.

Adapters must read window/process identity, foreground, geometry and elements
independently, then recheck these inside dispatch immediately before each input.
This contract does not make global Windows input atomic with focus changes.
"""
from copy import deepcopy
import math
import threading
import time


class NativeActionControl:
    def __init__(self, adapter, window, guard, *, clock=time.monotonic, max_age=3):
        if not isinstance(max_age, (int, float)) or not math.isfinite(max_age) or not 0 < max_age <= 10:
            raise ValueError('invalid_observation_lifetime')
        self.adapter, self.window, self.guard = adapter, deepcopy(window), guard
        self.clock, self.max_age = clock, max_age
        self.stopped = threading.Event()
        self._issued = None
        self._lock = threading.Lock()

    def stop(self):
        # Does not wait for a potentially blocked dispatch. Adapter cancellation
        # must release only its own held inputs, never arbitrary user keys.
        self.stopped.set()
        self.adapter.cancel()

    def _check(self):
        if self.stopped.is_set():
            raise RuntimeError('native_actions_stopped')
        self.guard()
        if self.stopped.is_set():
            raise RuntimeError('native_actions_stopped')

    def _read(self):
        self._check()
        state = deepcopy(self.adapter.read())
        if state.get('window') != self.window:
            raise ValueError('native_window_changed')
        if state.get('foreground') is not True:
            raise ValueError('native_focus_lost')
        if state.get('available') is not True:
            raise ValueError('native_window_unavailable')
        self._check()
        return state

    def observe(self):
        with self._lock:
            self._issued = None
            started = self.clock()
            state = self._read()
            snapshot = {'state': state, 'observed_at': started}
            self._issued = deepcopy(snapshot)
            return snapshot

    def _fresh(self, snapshot):
        age = self.clock() - snapshot['observed_at']
        if not math.isfinite(age) or not 0 <= age <= self.max_age:
            raise ValueError('native_observation_expired')

    @staticmethod
    def _action(action, state):
        if type(action) is not dict:
            raise ValueError('invalid_native_action')
        op = action.get('op')
        expected = {'op', 'target'} | ({'text'} if op == 'type' else {'key'} if op == 'key' else set())
        if op not in ('click', 'type', 'key') or set(action) != expected:
            raise ValueError('invalid_native_action')
        target = action['target']
        if type(target) is not str or not target:
            raise ValueError('invalid_native_target')
        matches = [e for e in state.get('elements', []) if e.get('id') == target]
        if len(matches) != 1:
            raise ValueError('native_target_missing_or_ambiguous')
        element = matches[0]
        if element.get('enabled') is not True or element.get('visible') is not True:
            raise ValueError('native_target_unavailable')
        if op not in element.get('actions', []):
            raise ValueError('native_action_not_allowed')
        if op in ('type', 'key') and element.get('focused') is not True:
            raise ValueError('native_input_target_not_focused')
        if op == 'type':
            value = action['text']
            if type(value) is not str or not value or len(value) > 4000 or any(ord(c) < 32 and c not in '\n\t' for c in value):
                raise ValueError('invalid_native_text')
        if op == 'key' and action['key'] not in element.get('allowed_keys', []):
            raise ValueError('native_key_not_allowed')

    def act(self, action, snapshot, verify):
        """verify is trusted application code, never a model-supplied expression."""
        with self._lock:
            issued, self._issued = self._issued, None
            try:
                self._check()
                if issued is None or snapshot != issued:
                    raise ValueError('unknown_native_observation')
                self._fresh(issued)
                before = self._read()
                if before != issued['state']:
                    raise ValueError('native_observation_changed')
                # A slow read must not extend observation lifetime.
                self._fresh(issued)
                action = deepcopy(action)
                self._action(action, before)
                if not callable(verify):
                    raise ValueError('native_verifier_required')
            except (ValueError, RuntimeError) as error:
                return {'status': 'refused', 'reason': str(error), 'verified': False}
            try:
                self._check()
                self._fresh(issued)
            except (ValueError, RuntimeError) as error:
                return {'status': 'refused', 'reason': str(error), 'verified': False}
            def cancelled():
                age = self.clock() - issued['observed_at']
                return self.stopped.is_set() or not math.isfinite(age) or not 0 <= age <= self.max_age
            try:
                self.adapter.dispatch(deepcopy(action), expected=deepcopy(before), cancelled=cancelled)
                after = self._read()
                verified = verify(action, before, after) is True
                self._check()
                return {'status': 'verified' if verified else 'unverified',
                        'verified': verified, 'after': after}
            except Exception as error:
                # Input may have happened even when the call failed. Never retry.
                result = {'status': 'uncertain', 'verified': False,
                          'reason': type(error).__name__}
                # Preserve only machine error codes, never provider text or data.
                code = str(error)
                if (code.startswith('native_') and len(code) <= 100
                        and all(c in 'abcdefghijklmnopqrstuvwxyz_' for c in code)):
                    result['code'] = code
                return result
