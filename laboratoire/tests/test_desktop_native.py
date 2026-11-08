from pathlib import Path
import sys
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from contextlib import contextmanager

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from desktop_native import DesktopNative, run_native_turn

TEXT = 'Ecris dans le bloc-notes le texte : validation_texte'


@pytest.mark.parametrize('source', ['twitch', 'discord', 'page', 'model'])
def test_external_sources_cannot_construct_backend(source):
    components = Mock()
    controller = DesktopNative(Mock(), components=components, guard=Mock())
    with pytest.raises(ValueError): controller.handle(TEXT, source)
    components.assert_not_called()


def test_example_never_constructs_backend():
    components = Mock()
    controller = DesktopNative(Mock(), components=components, guard=Mock())
    assert not controller.can_handle('Si je dis '+TEXT, 'text')
    controller.handle('Si je dis '+TEXT, 'text')
    components.assert_not_called()


def test_game_guard_refuses_before_pc_access():
    components = Mock()
    controller = DesktopNative(Mock(), components=components,
        guard=Mock(side_effect=RuntimeError('native_game_active')))
    result = controller.handle(TEXT, 'voice')
    assert not result['verified'] and 'jeu' in result['reply']
    components.assert_not_called()


def test_cancel_during_backend_construction_prevents_inventory():
    inventory = Mock()
    controller = DesktopNative(Mock(), guard=Mock())
    def components(guard):
        controller.cancel()
        return inventory, Mock()
    controller.components = components
    assert not controller.handle(TEXT, 'text')['verified']
    inventory.assert_not_called()


def app():
    return SimpleNamespace(stop=Event(), inputs=Queue(), speech_epoch=0,
        session=SimpleNamespace(voice=SimpleNamespace(interruption_epoch=0)),
        observation=Mock(), natives=Mock(), say=Mock())


@pytest.mark.parametrize('cancel', ['stop','new_input','voice_epoch'])
def test_interruption_suppresses_late_reply(cancel):
    instance=app()
    def handle(*args, cancelled):
        if cancel=='stop': instance.stop.set()
        if cancel=='new_input': instance.inputs.put('autre demande')
        if cancel=='voice_epoch': instance.session.voice.interruption_epoch += 1
        assert cancelled()
        return {'status':'unverified','verified':False,'reply':'stale'}
    instance.natives.handle.side_effect=handle
    run_native_turn(instance,TEXT,'text')
    instance.say.assert_not_called()


def test_result_text_is_not_emitted_in_technical_metrics():
    instance=app()
    instance.natives.handle.return_value={'status':'complete','verified':True,'reply':'result'}
    run_native_turn(instance,TEXT,'voice')
    instance.say.assert_called_once_with('result')
    assert 'validation_texte' not in repr(instance.observation.emit.call_args)


def test_native_action_listens_for_stop_and_closes_listener_before_reply():
    instance=app(); active=[]
    @contextmanager
    def listener():
        active.append(True)
        try: yield
        finally: active.pop()
    instance.session.voice.stop_listener=listener
    def handle(*args, cancelled):
        assert active and not cancelled()
        return {'status':'complete','verified':True,'reply':'result'}
    instance.natives.handle.side_effect=handle
    instance.say.side_effect=lambda text: assert_listener_closed(active)
    run_native_turn(instance,TEXT,'voice')
    instance.say.assert_called_once_with('result')


def assert_listener_closed(active):
    assert not active  # Speech can acquire the hearing worker next.


def test_stop_heard_during_native_action_cancels_and_suppresses_reply():
    instance=app(); active=[]
    @contextmanager
    def listener():
        active.append(True)
        try: yield
        finally: active.pop()
    instance.session.voice.stop_listener=listener
    def handle(*args, cancelled):
        assert active
        instance.session.voice.interruption_epoch+=1
        assert cancelled()
        return {'status':'interrupted','verified':False,'reply':'stale'}
    instance.natives.handle.side_effect=handle
    run_native_turn(instance,TEXT,'voice')
    assert not active
    instance.say.assert_not_called()
    instance.natives.cancel.assert_called_once()


def test_listener_failure_revokes_native_permission_and_never_claims_success():
    instance=app()
    @contextmanager
    def listener():
        yield
        raise RuntimeError('listener unavailable')
    instance.session.voice.stop_listener=listener
    instance.natives.handle.return_value={'status':'complete','verified':True,'reply':'result'}
    with pytest.raises(RuntimeError,match='listener unavailable'):
        run_native_turn(instance,TEXT,'text')
    instance.natives.cancel.assert_called_once()
    instance.say.assert_not_called()


def test_real_stop_listener_interrupts_native_turn_without_microphone():
    from hearing_link import Hearing
    from voice_link import Voice
    instance=app()
    voice=Voice(Mock())
    instance.session.voice=voice
    hearing=Hearing(Mock()); hearing.cancel=Mock()
    action_started=Event()
    def command(op, cancel_if):
        assert op=='stop_only'
        assert action_started.wait(2)
        return {'status':'stop'}
    hearing.command=Mock(side_effect=command)
    voice.stop_listener=lambda:hearing.stop_only(voice,enabled=True)
    def handle(*args, cancelled):
        action_started.set()
        assert voice.interrupted.wait(2)
        assert cancelled()
        return {'status':'interrupted','verified':False,'reply':'stale'}
    instance.natives.handle.side_effect=handle
    run_native_turn(instance,TEXT,'voice')
    assert voice.interruption_epoch==1
    hearing.cancel.assert_called_once()
    instance.say.assert_not_called()


def test_failed_hearing_cancels_native_action_before_next_input():
    from hearing_link import Hearing
    from voice_link import Voice
    instance=app(); voice=Voice(Mock()); instance.session.voice=voice
    hearing=Hearing(Mock()); hearing.cancel=Mock()
    action_started=Event(); failed=Event(); inputs=[]
    def command(op,cancel_if):
        assert action_started.wait(2)
        return {'status':'error'}
    hearing.command=Mock(side_effect=command)
    voice.stop_listener=lambda:hearing.stop_only(voice,enabled=True,
        on_status=lambda status:failed.set() if status=='error' else None)
    def handle(*args,cancelled):
        action_started.set()
        assert failed.wait(2)
        if not cancelled(): inputs.append('unexpected input')
        return {'status':'interrupted','verified':False,'reply':'stale'}
    instance.natives.handle.side_effect=handle
    with pytest.raises(RuntimeError,match='Ecoute stop indisponible'):
        run_native_turn(instance,TEXT,'voice')
    assert inputs==[]
    instance.say.assert_not_called()
    instance.natives.cancel.assert_called_once()
