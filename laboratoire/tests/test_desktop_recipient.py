import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from desktop_recipient import accept_speech
from desktop_initiative import DesktopInitiative


def app(mode='animation',channels=None):
    return SimpleNamespace(initiative=Mock(mode=mode),channels=channels,
        stream_recipient=Mock(),session=Mock(),observation=Mock(),events=Mock())


@pytest.mark.parametrize('address',['other','unclear'])
def test_other_speech_not_accepted_and_animation_not_disabled(address):
    a=app();a.stream_recipient.decide.return_value={'address':address}
    thought=Mock();history=[{'role':'assistant','content':'Sujet public'}]
    assert not accept_speech(a,{'text':'Alice, ne me réponds pas.','cleaned':'ne me réponds pas.'},history,thought)
    a.stream_recipient.decide.assert_called_once_with(a.session,'Alice, ne me réponds pas.')
    a.initiative.defer.assert_called_once_with(history,None,seconds=18)
    a.initiative.set_mode.assert_not_called()
    assert 'Alice, ne' not in repr(a.observation.mock_calls)


def test_direct_speech_passes_and_checks_session():
    a=app();a.stream_recipient.decide.return_value={'address':'alice'}
    assert accept_speech(a,{'text':'Alice, explique.'},[],Mock())
    a.session.check.assert_called_once();a.initiative.defer.assert_not_called()


def test_private_path_unchanged_without_extra_model_call():
    a=app('quiet')
    assert accept_speech(a,{},[],Mock())
    a.stream_recipient.reset.assert_called_once();a.stream_recipient.decide.assert_not_called()


def test_public_connection_keeps_filter_even_in_quiet():
    a=app('quiet',SimpleNamespace(enabled={'twitch':True}))
    a.stream_recipient.decide.return_value={'address':'other'}
    assert not accept_speech(a,{'text':'Le chat, bonjour !'},[],Mock())


def test_guard_failure_propagates_instead_of_ignoring_shutdown():
    a=app();a.stream_recipient.decide.return_value={'address':'unclear'}
    a.session.check.side_effect=RuntimeError('guard')
    with pytest.raises(RuntimeError):accept_speech(a,{},[],Mock())


def test_defer_preserves_animation_and_delays_next_attempt():
    import threading
    fake=SimpleNamespace(core=SimpleNamespace(lock=threading.RLock(),clock=lambda:100,
        next_attempt=105),idle=Mock(),mode='animation')
    DesktopInitiative.defer(fake,[],seconds=18)
    assert fake.core.next_attempt==118 and fake.mode=='animation'
    fake.core.next_attempt=140
    DesktopInitiative.defer(fake,[],seconds=18)
    assert fake.core.next_attempt==140
