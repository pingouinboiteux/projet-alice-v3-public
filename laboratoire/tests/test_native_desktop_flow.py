"""Native command routing through the ordinary widgets/loop, synthetic services."""
from unittest.mock import Mock, patch
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_search_desktop_flow as harness
from native_text_request import interpret


@pytest.fixture(autouse=True)
def desktop_root(validation_desktop_root):
    harness._desktop_root = validation_desktop_root
    yield
    harness._desktop_root = None


def native_controller():
    controller=Mock()
    controller.can_handle.side_effect=lambda text,source:interpret(text,source)['status']!='not_handled'
    controller.handle.return_value={'status':'complete','verified':True,'reply':'NATIVE_PRIVATE_SENTINEL'}
    return controller


def test_native_command_precedes_memory_and_web_routing():
    controller=native_controller()
    with patch('desktop_native.DesktopNative',return_value=controller):
        result=harness.run_loop(['Ecris dans le bloc-notes le texte : validation_texte','Bonjour'],Mock())
    controller.handle.assert_called_once()
    assert 'NATIVE_PRIVATE_SENTINEL' in result['spoken']
    result['memory'].answer.assert_called_once()
    assert 'NATIVE_PRIVATE_SENTINEL' not in repr(result['memory'].answer.call_args)
    result['router'].assert_called_once()
    assert result['finished']
    assert controller.cancel.call_count>=1


def test_example_reaches_conversation_without_native_action():
    controller=native_controller()
    with patch('desktop_native.DesktopNative',return_value=controller):
        result=harness.run_loop(['Si je dis ecris dans le bloc-notes le texte : exemple'],Mock())
    controller.handle.assert_not_called()
    result['memory'].answer.assert_called_once()
