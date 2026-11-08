"""Real desktop loop, fictional vault, inert services, no model or sound."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from test_search_desktop_flow import run_loop, desktop_interpreter
from test_protected_workspace import store
from unittest.mock import Mock

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
def test_code_request_is_refused_in_real_loop():
    result=run_loop(['/faire lance powershell'],Mock())
    assert any('Execution de code desactivee' in text for text in result['spoken'])
    result['confirm'].assert_not_called()
