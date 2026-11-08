from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from unittest.mock import Mock,patch
import pytest
from test_search_desktop_flow import run_loop,desktop_interpreter


@pytest.mark.usefixtures('desktop_interpreter')
def test_screen_request_bypasses_router_memory_and_action_tools():
    controller=Mock();controller.has_ready.return_value=False
    controller.handle.return_value='validation_constat_ecran'
    with patch('screen_observer.ScreenObserver',return_value=controller):
        result=run_loop(['Alice regarde mon ecran'],Mock())
    assert result['spoken']==['validation_constat_ecran']
    result['memory'].answer.assert_not_called();result['router'].assert_not_called()
    controller.close.assert_called_once()


@pytest.mark.usefixtures('desktop_interpreter')
def test_stop_is_a_local_control_without_model():
    controller=Mock();controller.has_ready.return_value=False
    controller.handle.return_value='Observation arretee'
    with patch('screen_observer.ScreenObserver',return_value=controller):
        result=run_loop(['/ecran stop'],Mock())
    assert not result['spoken']
    result['memory'].answer.assert_not_called();result['router'].assert_not_called()
