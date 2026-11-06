"""Exact user values, bound references and a side-effect-free pre-commit gate.

Only a trusted caller may construct this contract from explicit user values.
This module does not extract intent from natural language, OCR or model output.
The caller must read fresh application values immediately before commit and
keep the adapter's scope/revision checks; this gate does not authorize a save.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping


def _scalar(value):
    return type(value) in (str, bool, int, type(None)) or (
        type(value) is float and math.isfinite(value))


def _equal(left, right):
    # bool is a subclass of int; Python equality alone would accept True as 1.
    return type(left) is type(right) and left == right


@dataclass(frozen=True, init=False)
class ValueContract:
    _items: tuple

    @classmethod
    def from_user_values(cls, values):
        if not isinstance(values, Mapping) or not values:
            raise ValueError('explicit_user_values_required')
        items = []
        for field, value in values.items():
            if type(field) is not str or not field or not _scalar(value):
                raise ValueError('invalid_user_value')
            items.append((field, value))
        contract = object.__new__(cls)
        object.__setattr__(contract, '_items', tuple(items))
        return contract

    def references(self):
        """Return a fresh description; editing it cannot modify the contract."""
        return [{'field': field, 'value_ref': 'user:' + field, 'value': value}
                for field, value in self._items]

    def resolve(self, action):
        """Validate a proposed field change without executing or silently fixing it.

        value_ref explicitly requests a lossless binding. A wrong literal value
        is rejected, never replaced. Click/navigation actions belong to the
        adapter and are intentionally outside this method's scope.
        """
        if type(action) is not dict:
            raise ValueError('action_schema')
        op, target = action.get('op'), action.get('target')
        if type(op) is not str or op not in ('fill', 'select', 'check') or type(target) is not str:
            raise ValueError('action_schema')
        values = dict(self._items)
        if target not in values:
            raise ValueError('field_outside_contract')
        if set(action) == {'op', 'target', 'value_ref'}:
            if type(action['value_ref']) is not str or action['value_ref'] != 'user:' + target:
                raise ValueError('unknown_or_wrong_field_reference')
            value = values[target]
        elif set(action) == {'op', 'target', 'value'}:
            value = action['value']
            if not _scalar(value) or not _equal(value, values[target]):
                raise ValueError('literal_value_mismatch')
        else:
            raise ValueError('action_schema')
        if (op in ('fill', 'select') and type(value) is not str) or (op == 'check' and type(value) is not bool):
            raise ValueError('operation_value_type_mismatch')
        return {'op': op, 'target': target, 'value': value}

    def check_values(self, observed):
        """Compare all contracted fields exactly; extra unrelated fields are ignored."""
        if not isinstance(observed, Mapping):
            return {'ok': False, 'differences': [{'reason': 'observation_schema'}]}
        differences = []
        for field, expected in self._items:
            if field not in observed:
                differences.append({'field': field, 'reason': 'missing', 'expected': expected})
            elif not _scalar(observed[field]) or not _equal(observed[field], expected):
                actual = observed[field]
                differences.append({'field': field, 'reason': 'mismatch', 'expected': expected,
                                    'actual': actual if _scalar(actual) else None,
                                    'actual_type': type(actual).__name__})
        return {'ok': not differences, 'differences': differences}

    def check_observation(self, snapshot):
        """Adapter for the observer's visible element list; duplicates fail closed."""
        if type(snapshot) is not dict or type(snapshot.get('elements')) is not list:
            return {'ok': False, 'differences': [{'reason': 'observation_schema'}]}
        values, seen, errors = {}, set(), []
        contracted = dict(self._items)
        for element in snapshot['elements']:
            if type(element) is not dict or type(element.get('id')) is not str:
                return {'ok': False, 'differences': [{'reason': 'observation_schema'}]}
            field = element['id']
            if field not in contracted:
                continue
            if field in seen:
                errors.append({'field': field, 'reason': 'ambiguous'})
            seen.add(field)
            if 'value' in element:
                values[field] = element['value']
        result = self.check_values(values)
        result['differences'].extend(errors)
        result['ok'] = not result['differences']
        return result
