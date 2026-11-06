"""Pure action-boundary tests, no browser/GPU launch during unit tests."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_browser import BrowserDemo, validate_action


def observation():
    return {'scope': 'validation_test', 'revision': 1, 'page': 'form', 'status': 'Pret', 'saved': 'Aucun document enregistre',
            'elements': [
                {'id': 'title', 'role': 'textbox', 'value': '', 'enabled': True, 'options': []},
                {'id': 'category', 'role': 'combobox', 'value': 'personnel', 'enabled': True, 'options': [{'value': 'travail'}]},
                {'id': 'reminder', 'role': 'checkbox', 'value': False, 'enabled': True, 'options': []},
                {'id': 'send', 'role': 'button', 'value': None, 'enabled': False, 'options': []}]}


@pytest.mark.parametrize('action', [
    {'op': 'click', 'target': 'send'},
    {'op': 'click', 'target': 'title'},
    {'op': 'fill', 'target': 'title', 'value': 'x'*81},
    {'op': 'fill', 'target': 'title', 'value': 'line\nline'},
    {'op': 'check', 'target': 'reminder', 'value': 1},
    {'op': 'select', 'target': 'category', 'value': 'inconnu'},
    {'op': 'click', 'target': 'title"]'},
    {'op': 'fill', 'target': 'title', 'value': 'x', 'url': 'https://example.com'},
    {'op': 'shell', 'target': 'title'}])
def test_rejects_invalid_actions(action):
    with pytest.raises(ValueError): validate_action(action, observation())


def test_valid_actions_and_duplicate_id():
    snap = observation()
    assert validate_action({'op': 'fill', 'target': 'title', 'value': 'Lecture'}, snap)['id'] == 'title'
    assert validate_action({'op': 'check', 'target': 'reminder', 'value': True}, snap)['id'] == 'reminder'
    snap['elements'].append(copy.deepcopy(snap['elements'][0]))
    with pytest.raises(ValueError): validate_action({'op': 'fill', 'target': 'title', 'value': 'x'}, snap)


def test_modified_expired_or_changed_snapshots_never_touch_locator():
    now = [10.0]
    demo = BrowserDemo(lambda: None, clock=lambda: now[0])
    current = observation()
    demo._read = lambda: copy.deepcopy(current)
    snapshot = demo.observe()
    tampered = copy.deepcopy(snapshot); tampered['revision'] = 99
    assert not demo.act({'op': 'fill', 'target': 'title', 'value': 'X'}, tampered)['ok']
    snapshot = demo.observe(); now[0] = 30
    assert demo.act({'op': 'fill', 'target': 'title', 'value': 'X'}, snapshot)['reason'] == 'observation_expired'
    snapshot = demo.observe(); current['revision'] += 1
    assert demo.act({'op': 'fill', 'target': 'title', 'value': 'X'}, snapshot)['reason'] == 'observation_changed'


def test_readback_does_not_trust_successful_dispatch():
    before = observation(); after = copy.deepcopy(before)
    action = {'op': 'fill', 'target': 'title', 'value': 'Different'}
    assert not BrowserDemo._verify(action, before, after)
    after['elements'][0]['value'] = 'Different'
    assert BrowserDemo._verify(action, before, after)


def test_requires_guard():
    with pytest.raises(TypeError): BrowserDemo(None)
