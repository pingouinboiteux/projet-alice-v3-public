"""Real desktop loop, fictional vault, inert services, no model or sound."""
from pathlib import Path
import sys
from types import ModuleType
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from test_search_desktop_flow import run_loop, desktop_interpreter
from test_protected_workspace import store
from unittest.mock import Mock, patch


@pytest.fixture(autouse=True)
def public_screen_ocr_stub():
    """The OCR worker is private; these command tests never capture a screen."""
    worker = ModuleType('screen_ocr')
    worker.detect = Mock()
    with patch.dict(sys.modules, {'screen_ocr': worker}):
        yield

@pytest.mark.usefixtures('desktop_interpreter')
def test_document_request_uses_vault_before_model_and_memory(store,monkeypatch):
    store.write('validation.txt','Contenu fictif verifie',source='text')
    monkeypatch.setattr('protected_dialogue.Workspace',lambda:store)
    result=run_loop(['lis le document validation.txt'],Mock())
    assert ('text',('Documents proteges','Contenu fictif verifie')) in result['events']
    assert not any('Contenu fictif verifie' in text for text in result['spoken'])
    result['memory'].answer.assert_not_called()
    result['router'].assert_not_called()

@pytest.mark.usefixtures('desktop_interpreter')
def test_explicit_code_mission_uses_local_controller_without_memory_or_router():
    mission=Mock();mission.handle.return_value='Mission validation_123 executee dans l atelier.'
    with patch('code_missions.CodeMissions',return_value=mission):
        result=run_loop(['/faire cree validation.txt'],Mock())
    mission.handle.assert_called_once()
    assert ('text',('Mission de code','Mission validation_123 executee dans l atelier.')) in result['events']
    result['memory'].answer.assert_not_called()
    result['router'].assert_not_called()
    result['confirm'].assert_not_called()
