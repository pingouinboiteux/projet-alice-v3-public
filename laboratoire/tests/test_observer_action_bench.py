import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_action_bench import achieve, payload_for

def session_for(content, finish='stop'):
    session = Mock()
    session.model_spec = {'family': 'gemma4'}
    session.request.return_value = {'choices': [{'message': {'content': content}, 'finish_reason': finish}]}
    return session

def test_acknowledgement_alone_never_means_success():
    session = session_for('{"op":"click","target":"save"}')
    demo = Mock()
    demo.observe.return_value = {'saved': None}
    demo.act.return_value = {'ok': True, 'verified': True, 'reason': 'verified'}
    result = achieve(session, demo, 'save', lambda obs: obs['saved'] == 'expected', max_steps=2)
    assert not result['passed']
    assert result['reason'] == 'step_budget_exhausted'
    assert demo.act.call_count == 2

def test_observed_result_is_required():
    demo = Mock()
    demo.observe.side_effect = [{'saved': None}, {'saved': 'expected'}]
    demo.act.return_value = {'ok': True, 'verified': True, 'reason': 'verified'}
    result = achieve(session_for('{"op":"click","target":"save"}'), demo,
                     'save', lambda obs: obs['saved'] == 'expected')
    assert result['passed']

@pytest.mark.parametrize('content,finish', [('{"op":"done"}', 'stop'), ('{}', 'length')])
def test_premature_done_or_truncation_cannot_act(content, finish):
    demo = Mock()
    demo.observe.return_value = {'saved': None}
    result = achieve(session_for(content, finish), demo, 'save', lambda obs: False)
    assert not result['passed']
    demo.act.assert_not_called()

def test_guard_failure_prevents_observation_and_model():
    session = session_for('{}')
    session.check.side_effect = RuntimeError('fps')
    demo = Mock()
    with pytest.raises(RuntimeError, match='fps'):
        achieve(session, demo, 'save', lambda obs: False)
    demo.observe.assert_not_called()
    session.request.assert_not_called()

def test_goal_and_observation_are_the_only_user_inputs():
    data = json.loads(payload_for('goal', {'elements': []})['messages'][1]['content'])
    assert data == {'demande': 'goal', 'observation': {'elements': []}, 'actions_precedentes': []}
