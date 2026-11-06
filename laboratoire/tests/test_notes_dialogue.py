"""Synthetic note controller; no real database, browser, audio or model."""
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from notes_dialogue import NotesDialogue, interpret

TARGET={'title':'validation_note','body':'Garder  deux espaces et le mot stop.'}
REQUEST='Cree une note titre validation_note texte Garder deux espaces.'

def make():
    clock=[0.]
    backend=Mock()
    backend.title_exists.return_value=False
    backend.verify_persisted.return_value=True
    planner=Mock(return_value={'status':'ready','target':dict(TARGET)})
    def execute(session,app,target,claim):
        assert claim()==target
        return {'passed':True}
    factory=Mock(return_value=backend)
    value=NotesDialogue(Mock(),factory=factory,planner=planner,executor=execute,clock=lambda:clock[0])
    return value,backend,factory,planner,clock

def test_construction_is_lazy_and_save_requires_confirmation_and_verification():
    value,backend,factory,planner,clock=make();factory.assert_not_called()
    confirm=Mock(return_value=True)
    result=value.handle(REQUEST,'text',confirm)
    assert result['status']=='saved'
    assert TARGET['body'] in confirm.call_args.args[0]
    backend.verify_persisted.assert_called_once_with(TARGET)
    backend.close.assert_called_once()
    assert value.turns==[]

def test_decline_does_not_open_backend_and_corrected_request_gets_new_review():
    value,backend,factory,planner,clock=make()
    assert value.handle(REQUEST,'text',lambda _:False)['status']=='cancelled'
    factory.assert_not_called()
    corrected='Finalement remplace le texte par Arroser le jardin.'
    assert value.can_handle(corrected)
    planner.return_value={'status':'ready','target':{'title':'validation_note','body':'Arroser le jardin.'}}
    assert value.handle(corrected,'text',lambda _:True)['status']=='saved'
    assert planner.call_args.args[1]==[REQUEST,corrected]

def test_missing_values_and_expired_followup_do_not_open_backend():
    value,backend,factory,planner,clock=make()
    planner.return_value={'status':'clarify'}
    assert value.handle('Cree une note pour demain','text',lambda _:True)['status']=='clarify'
    factory.assert_not_called()
    assert value.can_handle('Titre Jardin texte Arroser.')
    clock[0]=301
    assert not value.can_handle('Titre Jardin texte Arroser.')

def test_voice_requires_visual_review_but_uses_same_exact_values():
    value,backend,factory,planner,clock=make()
    planner.return_value={'status':'needs_confirmation','target':TARGET}
    confirm=Mock(return_value=True)
    assert value.handle(REQUEST,'voice',confirm)['status']=='saved'
    assert 'Transcription vocale' in confirm.call_args.args[0]
    assert planner.call_args.args[2]=='voice'

@pytest.mark.parametrize('source',['twitch','discord','system',None])
def test_external_source_never_enters_planning(source):
    value,backend,factory,planner,clock=make()
    with pytest.raises(ValueError):value.handle(REQUEST,source,lambda _:True)
    planner.assert_not_called();factory.assert_not_called()

def test_duplicate_title_never_replaces_existing_note():
    value,backend,factory,planner,clock=make();backend.title_exists.return_value=True
    assert value.handle(REQUEST,'text',lambda _:True)['status']=='exists'
    backend.prepare_new.assert_not_called();backend.close.assert_called_once()

def test_failed_disk_verification_never_reports_success():
    value,backend,factory,planner,clock=make();backend.verify_persisted.return_value=False
    assert value.handle(REQUEST,'text',lambda _:True)['status']=='unverified'

def test_input_during_confirmation_invalidates_authorization():
    value,backend,factory,planner,clock=make()
    def confirm(description):
        value.pending.cancel()
        return True
    assert value.handle(REQUEST,'text',confirm)['status']=='failed'
    factory.assert_not_called()

def test_input_after_confirmation_prevents_commit():
    value,backend,factory,planner,clock=make()
    backend.prepare_new.side_effect=value.pending.cancel
    assert value.handle(REQUEST,'text',lambda _:True)['status']=='failed'
    backend.verify_persisted.assert_not_called();backend.close.assert_called_once()

def test_review_expires_before_commit():
    value,backend,factory,planner,clock=make()
    backend.prepare_new.side_effect=lambda:clock.__setitem__(0,61)
    assert value.handle(REQUEST,'text',lambda _:True)['status']=='failed'
    backend.verify_persisted.assert_not_called()

@pytest.mark.parametrize('text',['Bonjour','Ne cree pas de note','Il a dit "cree une note"',
                              'Comment creer une note ?'])
def test_normal_conversation_not_captured(text):
    value,*_=make()
    assert not value.can_handle(text)

def test_quoted_stop_is_content_not_cancelled_request():
    value,*_=make()
    assert value.can_handle('Cree une note titre Salut texte "stop"')

def test_real_parser_rejects_model_invented_content():
    session=Mock()
    session.ask.return_value=('{"intent":"create_note","title":{"turn":0,"quote":"validation_note"},"body":{"turn":0,"quote":"INVENTED"}}',0,{})
    assert interpret(session,[REQUEST],'local_text')['status']=='clarify'

def test_browser_cleanup_after_guard_kill_checks_owned_processes():
    from types import SimpleNamespace
    from observer_browser import BrowserDemo
    value=SimpleNamespace(_closed_once=False,_record_descendants=Mock(),
        browser=Mock(),_playwright=Mock(),stop_owned=Mock(),owned_stopped=True)
    value.browser.close.side_effect=RuntimeError('Driver already killed')
    BrowserDemo.close(value)
    value.stop_owned.assert_called_once()
    value._closed_once=False;value.owned_stopped=False
    with pytest.raises(RuntimeError):BrowserDemo.close(value)

def test_duplicate_keeps_context_for_explicit_title_correction():
    value,backend,factory,planner,clock=make();backend.title_exists.return_value=True
    assert value.handle(REQUEST,'text',lambda _:True)['status']=='exists'
    assert value.can_handle('Finalement remplace le titre par validation_autre')
