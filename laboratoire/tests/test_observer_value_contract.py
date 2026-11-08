import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_value_contract import ValueContract


def test_bound_reference_preserves_literal_markup_and_unicode():
    text = '  Verifier <b>cafe\u0301</b> & "prix" 😀  '
    contract = ValueContract.from_user_values({'title': text})
    action = contract.resolve({'op': 'fill', 'target': 'title', 'value_ref': 'user:title'})
    assert action == {'op': 'fill', 'target': 'title', 'value': text}
    assert contract.check_values({'title': text})['ok']
    assert not contract.check_values({'title': text.strip()})['ok']
    assert not contract.check_values({'title': text.replace('e\u0301', '\u00e9')})['ok']


def test_contract_and_exports_do_not_share_mutable_state():
    original = {'title': 'original'}
    contract = ValueContract.from_user_values(original)
    original['title'] = 'changed'
    exported = contract.references()
    exported[0]['value'] = 'forged'
    assert contract.check_values({'title': 'original'})['ok']
    with pytest.raises(FrozenInstanceError):
        contract._items = ()


@pytest.mark.parametrize('action', [
    {'op': 'fill', 'target': 'title', 'value': 'Text'},
    {'op': 'fill', 'target': 'title', 'value_ref': 'user:other'},
    {'op': 'fill', 'target': 'other', 'value_ref': 'user:title'},
    {'op': 'fill', 'target': 'title', 'value_ref': 'user:title', 'value': 'Text'},
    {'op': 'fill', 'target': 'title', 'value_ref': 'user:title', 'execute': True},
    {'op': 'click', 'target': 'save'},
    {'op': ['fill'], 'target': 'title', 'value': 'Text'},
])
def test_forged_or_mismatching_actions_are_rejected(action):
    contract = ValueContract.from_user_values({'title': '<b>Text</b>'})
    with pytest.raises(ValueError):
        contract.resolve(action)


def test_bool_is_not_integer_and_reference_cannot_change_field_type():
    contract = ValueContract.from_user_values({'count': 1, 'reminder': True})
    assert not contract.check_values({'count': True, 'reminder': 1})['ok']
    with pytest.raises(ValueError, match='literal_value_mismatch'):
        contract.resolve({'op': 'check', 'target': 'reminder', 'value': 1})
    with pytest.raises(ValueError, match='operation_value_type_mismatch'):
        contract.resolve({'op': 'fill', 'target': 'reminder', 'value_ref': 'user:reminder'})
    assert contract.resolve({'op': 'check', 'target': 'reminder', 'value_ref': 'user:reminder'})['value'] is True


def test_gate_returns_all_missing_and_changed_fields_without_mutating_input():
    contract = ValueContract.from_user_values({'title': '<b>x</b>', 'reminder': False, 'category': 'travail'})
    observed = {'title': 'x', 'reminder': False}
    result = contract.check_values(observed)
    assert not result['ok']
    assert [(x['field'], x['reason']) for x in result['differences']] == [('title', 'mismatch'), ('category', 'missing')]
    assert observed == {'title': 'x', 'reminder': False}


def test_visible_snapshot_requires_unique_fields_with_values():
    contract = ValueContract.from_user_values({'title': 'x'})
    assert contract.check_observation({'elements': [{'id': 'title', 'value': 'x'}]})['ok']
    assert not contract.check_observation({'elements': [{'id': 'title'}]})['ok']
    result = contract.check_observation({'elements': [{'id': 'title', 'value': 'x'}, {'id': 'title', 'value': 'x'}]})
    assert not result['ok']
    assert result['differences'][0]['reason'] == 'ambiguous'


@pytest.mark.parametrize('values', [{}, {'x': []}, {'x': float('nan')}, {'x': float('inf')}, {1: 'x'}])
def test_only_explicit_scalar_mapping_can_create_contract(values):
    with pytest.raises(ValueError):
        ValueContract.from_user_values(values)
