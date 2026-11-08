"""Independent adversarial checks of the demo boundary; no browser launch."""
import copy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_browser import BrowserDemo, validate_action


def snapshot():
    return {'scope': 'validation_contract', 'revision': 1, 'page': 'form',
            'status': 'Pret', 'saved': None,
            'elements': [{'id': 'title', 'role': 'textbox', 'label': 'Titre',
                          'value': '', 'enabled': True, 'options': []}]}


def demo_for(current, clock=lambda: 1.):
    demo = BrowserDemo(guard=Mock(), clock=clock)
    demo._read = lambda: copy.deepcopy(current)
    demo.page = Mock()
    return demo


def test_forged_snapshot_cannot_enable_disabled_control():
    current = snapshot()
    current['elements'][0]['enabled'] = False
    demo = demo_for(current)
    observed = demo.observe()
    observed['elements'][0]['enabled'] = True
    result = demo.act({'op': 'fill', 'target': 'title', 'value': 'hello'}, observed)
    assert not result['ok']
    assert result['reason'] == 'unknown_or_modified_observation'
    demo.page.locator.assert_not_called()


def test_unversioned_dom_mutation_is_also_rejected():
    current = snapshot()
    demo = demo_for(current)
    observed = demo.observe()
    current['elements'][0]['value'] = 'Changed outside agent'
    result = demo.act({'op': 'fill', 'target': 'title', 'value': 'hello'}, observed)
    assert result['reason'] == 'observation_changed'
    demo.page.locator.assert_not_called()


def test_clock_reversal_invalidates_capability():
    now = [5.]
    demo = demo_for(snapshot(), clock=lambda: now[0])
    observed = demo.observe()
    now[0] = 4.
    result = demo.act({'op': 'fill', 'target': 'title', 'value': 'hello'}, observed)
    assert result['reason'] == 'observation_expired'
    demo.page.locator.assert_not_called()


def test_guard_failure_before_dispatch_never_touches_locator():
    demo = demo_for(snapshot())
    observed = demo.observe()
    demo.guard.side_effect = RuntimeError('fps unavailable')
    with pytest.raises(RuntimeError, match='fps unavailable'):
        demo.act({'op': 'fill', 'target': 'title', 'value': 'hello'}, observed)
    demo.page.locator.assert_not_called()


@pytest.mark.parametrize('target', ['Titre', '#title', 'title,body', 'send_message', '../../x'])
def test_target_is_exact_capability_not_label_selector_or_path(target):
    with pytest.raises(ValueError, match='target_outside_scope'):
        validate_action({'op': 'fill', 'target': target, 'value': 'x'}, snapshot())


def test_duplicate_id_is_ambiguous_even_with_same_visible_state():
    state = snapshot()
    state['elements'].append(copy.deepcopy(state['elements'][0]))
    with pytest.raises(ValueError, match='target_missing_or_ambiguous'):
        validate_action({'op': 'fill', 'target': 'title', 'value': 'x'}, state)


def test_undo_needs_actual_previous_state_not_just_acknowledgement():
    before, after, expected = snapshot(), snapshot(), snapshot()
    before['revision'] = 2
    after['revision'] = 3
    after['status'] = 'Modification annulee'
    expected['elements'][0]['value'] = 'original'
    assert not BrowserDemo._verify({'op': 'click', 'target': 'undo'}, before, after, expected)
    after['elements'][0]['value'] = 'original'
    assert BrowserDemo._verify({'op': 'click', 'target': 'undo'}, before, after, expected)
