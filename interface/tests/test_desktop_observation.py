"""Resource worker contracts, with no hardware, service or real-time wait."""
import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from desktop_observation import observe


def run_worker(*, session=None, iterations=1, cpu=12, failure=None, gpu_failure=None):
    finished = Mock()
    finished.is_set.side_effect = [False] * iterations + [True]
    app = SimpleNamespace(finished=finished, session=session,
                          observation=Mock(), events=queue.Queue())
    monitor = Mock()
    monitor.sample.return_value = dict(ram_free_gib=8, cpu_percent=cpu,
                                      games=[], programs=['validation_process'])
    monitor.sample.side_effect = failure
    tools = SimpleNamespace(Monitor=Mock(return_value=monitor), gpu_memory=Mock())
    tools.gpu_memory.return_value = [dict(alice_gpu=True, dedicated_used_gib=2, capacity_gib=8)]
    tools.gpu_memory.side_effect = gpu_failure
    clock = SimpleNamespace(time=lambda: 100, monotonic=lambda: 100)
    observe(app, tools, clock)
    return app, tools


def test_samples_without_session_and_gpu_refresh_throttled():
    app, tools = run_worker(iterations=2, cpu=None)
    tools.Monitor.assert_called_once_with()
    tools.gpu_memory.assert_called_once_with()
    sample = app.observation.sample.call_args_list[0].kwargs
    assert sample['ram_free_gib'] == 8
    assert sample['cpu_ram_at'] == 100
    assert sample['fps_available'] is False
    assert sample['fps_protection'] is False
    assert sample['child_states'] == {}
    app.observation.sample.assert_any_call(gpu_used_gib=2, gpu_capacity_gib=8, gpu_at=100)
    assert app.events.get_nowait() == ('resources',
        'RAM libre : 8 Gio | CPU : ? % | GPU Alice : 2/8 Gio utilises')
    assert app.finished.wait.call_count == 2
    app.finished.wait.assert_called_with(2)


def test_guard_snapshot_and_child_states_are_forwarded():
    session = SimpleNamespace(children={'validation_alive': Mock(), 'validation_dead': Mock()},
        fps_protection=True, ram_protection=True, reason=None,
        frame_guard=SimpleNamespace(report={'stop_reason': 'validation_reason', 'samples': [{
            'utc': '1970-01-01T00:01:00+00:00', 'frames': {'average_fps': 60},
            'display_frames': {'average_fps': 59}, 'game_focus': {'foreground': True}}]}))
    session.children['validation_alive'].poll.return_value = None
    session.children['validation_dead'].poll.return_value = 0
    app, _ = run_worker(session=session)
    sample = app.observation.sample.call_args_list[0].kwargs
    assert (sample['fps'], sample['displayed_fps'], sample['fps_at']) == (60, 59, 60)
    assert (sample['alive_children'], sample['dead_children']) == (1, 1)
    assert sample['child_states'] == {'validation_alive': 'running', 'validation_dead': 'stopped'}
    assert sample['guard_stopped'] and sample['fps_protection'] and sample['ram_protection']
    assert sample['game_foreground'] is True


@pytest.mark.parametrize('gpu', [False, True])
def test_measurement_errors_are_reported_without_stopping_worker(gpu):
    args = {'gpu_failure' if gpu else 'failure': ValueError('validation_private_detail')}
    app, _ = run_worker(**args)
    app.observation.emit.assert_called_once_with(
        'resource.gpu_error' if gpu else 'resource.error', {'error_type': 'ValueError'})
    event = app.events.get_nowait()
    assert event[0] == 'resources' and 'indisponible' in event[1]
    assert 'validation_private_detail' not in repr(app.observation.mock_calls)
    app.finished.wait.assert_called_once_with(2)


def test_application_delegates_with_its_existing_dependencies(monkeypatch):
    import alice_desktop
    import desktop_observation
    worker = Mock()
    monkeypatch.setattr(desktop_observation, 'observe', worker)
    app = object()
    alice_desktop.Application.observe(app)
    worker.assert_called_once_with(app, alice_desktop.pc_tools, alice_desktop.time)
