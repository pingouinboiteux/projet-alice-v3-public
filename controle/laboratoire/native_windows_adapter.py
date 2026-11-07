"""Bind observed Windows controls to explicit task grants and native input.

Not enabled by the desktop. Grants must come from trusted task/consent policy,
never page text or the model's proposed action. No foreground activation.
"""
from copy import deepcopy
import math
import threading

from .native_action_control import NativeActionControl


KEYS = frozenset(('Tab', 'Escape', 'Left', 'Right', 'Up', 'Down', 'Home', 'End'))


def rectangle(value):
    if type(value) not in (list, tuple) or len(value) != 4:
        raise ValueError('native_rectangle_missing')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError('native_rectangle_invalid')
    if value[2] <= 0 or value[3] <= 0:
        raise ValueError('native_rectangle_empty')
    return value


class NativeWindowsAdapter:
    def __init__(self, observer, transport, grants, guard, *, typing_context=None):
        self.observer, self.transport, self.guard = observer, transport, guard
        self.grants = deepcopy(grants)
        self.typing_context = typing_context
        self.stopped = threading.Event()
        for target, grant in self.grants.items():
            if type(target) is not str or not target or type(grant) is not dict:
                raise ValueError('invalid_native_grant')
            if set(grant) - {'actions', 'keys'} or not set(grant.get('actions', ())) <= {'click', 'type', 'key'}:
                raise ValueError('invalid_native_grant')
            if not set(grant.get('keys', ())) <= KEYS:
                raise ValueError('invalid_native_key_grant')

    def cancel(self):
        self.stopped.set()
        self.transport.cancel()

    def read(self):
        state = deepcopy(self.observer.read())
        rectangle(state['geometry'])
        if state.get('truncated') is not False:
            raise ValueError('native_incomplete_observation')
        seen = set()
        for element in state['elements']:
            target = element['id']
            if type(target) is not str or not target or target in seen:
                raise ValueError('native_ambiguous_element_identity')
            seen.add(target)
            # Read-only by default, even for enabled controls.
            grant = self.grants.get(target, {})
            element['actions'] = sorted(grant.get('actions', ()))
            element['allowed_keys'] = sorted(grant.get('keys', ()))
            if element.get('password') is not False:
                element['actions'] = []
                element['allowed_keys'] = []
                element['value'] = None
        return state

    @staticmethod
    def _stable(state, target, typing):
        result = deepcopy(state)
        if typing:
            # UIA document containers may expose the edit's text as well.
            # Only follow the observed ancestry, never unrelated text controls.
            by_id = {e['id']: e for e in result['elements']}
            ancestors = set()
            current = target
            while current in by_id and current not in ancestors:
                ancestors.add(current)
                current = by_id[current].get('parent_id')
            for element in result['elements']:
                if element['id'] in ancestors:
                    element['value'] = None
        return result

    def dispatch(self, action, *, expected, cancelled):
        # Also enforce grants when called without NativeActionControl.
        NativeActionControl._action(action, expected)
        target = action['target']
        grant = self.grants.get(target, {})
        if action['op'] not in grant.get('actions', ()):
            raise ValueError('native_action_without_grant')
        if action['op'] == 'key' and action['key'] not in grant.get('keys', ()):
            raise ValueError('native_key_without_grant')
        count = [0]
        def preflight():
            if self.stopped.is_set() or cancelled():
                raise RuntimeError('native_input_cancelled')
            self.guard()
            fresh = self.read()
            if fresh.get('foreground') is not True or fresh.get('available') is not True:
                raise RuntimeError('native_focus_or_window_lost')
            typing = action['op'] == 'type' and count[0] > 0
            if action['op'] == 'type':
                initial=next(e for e in expected['elements'] if e['id']==target).get('value')
                current=next((e.get('value') for e in fresh['elements'] if e['id']==target),None)
                if type(initial) is not str or current != initial + action['text'][:count[0]]:
                    raise RuntimeError('native_text_changed_between_batches')
            stable_fresh = self._stable(fresh, target, typing)
            stable_expected = self._stable(expected, target, typing)
            if action['op'] == 'type' and self.typing_context is not None:
                if self.typing_context.target != target:
                    raise RuntimeError('native_typing_context_target_mismatch')
                projected_fresh = self.typing_context.project(stable_fresh)
                projected_expected = self.typing_context.project(stable_expected)
                if typing:
                    stable_fresh, stable_expected = projected_fresh, projected_expected
            if stable_fresh != stable_expected:
                raise RuntimeError('native_target_changed_before_input')
            NativeActionControl._action(action, fresh)
            if action['op'] == 'click':
                hit = self.observer.hit_test(*point)
                parents = {e['id']: e.get('parent_id') for e in fresh['elements']}
                visited = set()
                while hit in parents and hit != target and hit not in visited:
                    visited.add(hit)
                    hit = parents[hit]
                if hit != target:
                    raise RuntimeError('native_click_obstructed')
            self.guard()
            if self.stopped.is_set() or cancelled():
                raise RuntimeError('native_input_cancelled')
            count[0] += 1
        if action['op'] == 'click':
            element = next(e for e in expected['elements'] if e['id'] == target)
            x, y, width, height = rectangle(element['rect'])
            left, top, ww, hh = rectangle(expected['geometry'])
            point = (int(x + width / 2), int(y + height / 2))
            if not (left <= point[0] < left + ww and top <= point[1] < top + hh):
                raise ValueError('native_click_outside_window')
            self.transport.click(*point, preflight=preflight, cancelled=cancelled)
        elif action['op'] == 'type':
            self.transport.type_text(action['text'], preflight=preflight, cancelled=cancelled)
        else:
            self.transport.key_tap(action['key'], preflight=preflight, cancelled=cancelled)
