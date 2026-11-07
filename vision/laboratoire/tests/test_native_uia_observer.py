"""Contract tests only: no real desktop, UIA provider or user process."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'laboratoire' / 'scripts'))
from native_uia_observer import UIAObserver


WINDOW = {'hwnd': 123, 'pid': 456, 'created': 100.5}


def test_persistent_reader_preserves_identity_and_hit_test_contract():
    worker = Mock(); worker.request.return_value = payload()
    runner = Mock(side_effect=AssertionError('must not launch per read'))
    reader = UIAObserver(WINDOW, runner=runner, worker=worker,
        process_factory=lambda pid: SimpleNamespace(is_running=lambda: True, create_time=lambda: 100.5))
    assert reader.read()['window'] == WINDOW
    assert reader.hit_test(-10, 25) == '1.2'
    assert worker.request.call_args_list[0].args == ('read',)
    assert worker.request.call_args_list[1].kwargs == {'x': -10, 'y': 25}
    runner.assert_not_called()


def payload():
    check = {'hwnd': 123, 'pid': 456, 'foreground': True, 'available': True}
    return {'checks_before': deepcopy(check), 'checks_after': deepcopy(check),
            'geometry': [0, 0, 500, 400], 'truncated': False, 'hit_id': '1.2',
            'elements': [{'id': '1.2', 'name': 'validation_field', 'type': 'ControlType.Edit',
                          'rect': [10, 10, 40, 20], 'enabled': True, 'visible': True,
                          'focused': True, 'value': 'validation_text', 'password': False}]}


def observer(data=None, runner=None, process=None):
    return UIAObserver(WINDOW, runner=runner or (lambda *a, **k: SimpleNamespace(stdout=json.dumps(data or payload()))),
                       process_factory=process or (lambda pid: SimpleNamespace(is_running=lambda: True,
                                                                              create_time=lambda: 100.5)))


def test_read_contract_and_bounded_hidden_runner():
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='\ufeff' + json.dumps(payload()))
    state = observer(runner=run).read()
    assert state['window'] == WINDOW and state['available'] and state['foreground']
    assert state['elements'][0]['value'] == 'validation_text'
    assert calls[0][1]['timeout'] == 8 and calls[0][1]['check'] is True
    assert calls[0][1]['encoding'] == 'utf-8'
    assert '-NonInteractive' in calls[0][0]
    assert not Path(calls[0][0][5]).is_absolute()
    root = Path(__file__).resolve().parents[3]
    assert calls[0][1]['cwd'] == root
    assert calls[0][0][5] == 'vision/laboratoire/native_uia_snapshot.ps1'
    assert (calls[0][1]['cwd'] / calls[0][0][5]).is_file()


@pytest.mark.parametrize('phase', ['checks_before', 'checks_after'])
@pytest.mark.parametrize('key,value', [('pid', 999), ('hwnd', 999), ('foreground', False), ('available', False)])
def test_changed_window_refused(phase, key, value):
    data = payload()
    data[phase][key] = value
    with pytest.raises(RuntimeError):
        observer(data).read()


@pytest.mark.parametrize('selected', [True, False, None])
def test_selection_state_preserved(selected):
    data = payload()
    data['elements'][0].update(type='ControlType.TabItem', selected=selected)
    assert observer(data).read()['elements'][0]['selected'] is selected


def test_missing_selection_pattern_defaults_to_unknown():
    assert observer().read()['elements'][0]['selected'] is None


@pytest.mark.parametrize('selected', [0, 1, 'true', '', [], {}])
def test_invalid_selection_state_refused(selected):
    data = payload()
    data['elements'][0]['selected'] = selected
    with pytest.raises(ValueError, match='invalid_native_selected_flag'):
        observer(data).read()


@pytest.mark.parametrize('after', [False, True])
def test_reused_pid_refused_before_and_after(after):
    count = []
    def process(pid):
        count.append(pid)
        created = 101 if len(count) > int(after) else 100.5
        return SimpleNamespace(is_running=lambda: True, create_time=lambda: created)
    with pytest.raises(RuntimeError, match='process_changed'):
        observer(process=process).read()


def test_dead_process_refused():
    with pytest.raises(RuntimeError):
        observer(process=lambda pid: SimpleNamespace(is_running=lambda: False)).read()


@pytest.mark.parametrize('error', [subprocess.TimeoutExpired('validation', 8),
                                 subprocess.CalledProcessError(1, 'validation')])
def test_provider_failure_propagates(error):
    def runner(*args, **kwargs):
        raise error
    with pytest.raises(type(error)):
        observer(runner=runner).read()


@pytest.mark.parametrize('rect', [[0, 0, float('nan'), 1], [0, 0, 1, float('inf')],
                                 [0, 0, -1, 1], [0, True, 1, 1], [0, 1]])
@pytest.mark.parametrize('element', [True, False])
def test_invalid_geometry_refused(rect, element):
    data = payload()
    if element:
        data['elements'][0]['rect'] = rect
    else:
        data['geometry'] = rect
    with pytest.raises(ValueError):
        observer(data).read()


def test_password_defense_and_truncation_exposed():
    data = payload()
    data['truncated'] = True
    data['elements'][0]['password'] = True
    state = observer(data).read()
    assert state['elements'][0]['name'] == '' and state['elements'][0]['value'] is None
    assert state['truncated'] is True


def test_parent_relationship_preserved_and_invalid_parent_refused():
    data = payload()
    child = deepcopy(data['elements'][0])
    child.update(id='1.3', parent_id='1.2')
    data['elements'].append(child)
    assert observer(data).read()['elements'][1]['parent_id'] == '1.2'
    child['parent_id'] = 'missing'
    with pytest.raises(ValueError, match='invalid_native_parent'):
        observer(data).read()


@pytest.mark.parametrize('mutation', ['duplicate', 'oversize', 'bad_bool', 'too_many'])
def test_malformed_elements_refused(mutation):
    data = payload()
    if mutation == 'duplicate':
        data['elements'] *= 2
    elif mutation == 'oversize':
        data['elements'][0]['value'] = 'x' * 4001
    elif mutation == 'bad_bool':
        data['elements'][0]['enabled'] = 1
    else:
        data['elements'] *= 201
    with pytest.raises(ValueError):
        observer(data).read()


def test_hit_test_and_point_validation():
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps(payload()))
    assert observer(runner=run).hit_test(-10, 25) == '1.2'
    assert calls[0][-5:] == ['-HitTest', '-PointX', '-10', '-PointY', '25']
    for x in (True, 1.2, float('nan'), 2**31):
        with pytest.raises(ValueError):
            observer(runner=run).hit_test(x, 0)
    assert len(calls) == 1


def test_script_ascii_and_no_input_primitives():
    script = Path(__file__).resolve().parents[1] / 'native_uia_snapshot.ps1'
    source = script.read_bytes().decode('ascii')
    assert 'FromHandle($handle)' in source and 'GetText(4001)' in source
    assert 'FromPoint($point)' in source and 'WindowFromPoint($nativePoint)' in source
    assert 'SelectionItemPattern]::Pattern' in source and '$selectionPattern.Current.IsSelected' in source
    assert all(word not in source for word in ('SendInput', 'SetFocus', 'InvokePattern', 'SetValue'))
