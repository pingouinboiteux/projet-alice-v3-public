from unittest.mock import Mock,patch
import pytest
from chat import Session


def test_fps_disabled_does_not_stop_on_game():
    with patch('chat.free_ram',return_value=8*1024**3),patch('chat.processes',return_value={'league of legends.exe'}) as processes:
        session=Session(allow_game=True,fps_protection=False)
        session.done=Mock();session.done.wait.side_effect=[False]*5+[True]
        session.stop_owned=Mock()
        session.watch()
        assert session.reason is None
        session.stop_owned.assert_not_called()
        processes.assert_not_called()


def test_ram_still_stops_when_fps_disabled():
    with patch('chat.free_ram',side_effect=[8*1024**3,5*1024**3]):
        session=Session(allow_game=True,fps_protection=False)
        session.done=Mock();session.done.wait.return_value=False
        session.stop_owned=Mock()
        session.watch()
        assert '6 Gio' in session.reason
        session.stop_owned.assert_called_once()


def test_interactive_ram_stop_can_be_disabled_without_losing_measurements():
    with patch('chat.free_ram',side_effect=[8*1024**3,5*1024**3]):
        session=Session(allow_game=True,fps_protection=False,ram_protection=False)
        session.done=Mock();session.done.wait.side_effect=[False,True]
        session.stop_owned=Mock()
        session.watch()
        assert session.reason is None and session.minimum_ram==5*1024**3
        session.stop_owned.assert_not_called()


def test_startup_ram_guard_stays_default_but_is_optional_for_interactive_alice():
    with patch('chat.free_ram',return_value=5*1024**3),patch('chat.processes',return_value=set()),patch('chat.verify_resources',side_effect=ValueError('validation_no_model')) as verify:
        with pytest.raises(RuntimeError,match='6 Gio'):Session().start()
        verify.assert_not_called()
        with pytest.raises(ValueError,match='validation_no_model'):Session(ram_protection=False).start()
        verify.assert_called_once()
