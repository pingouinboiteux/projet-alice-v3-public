"""Ordinary desktop loop with synthetic services only, no personal data."""
from contextlib import ExitStack
import gc
import os
import tkinter as tk
from unittest.mock import Mock,MagicMock,patch
import pytest
import alice_desktop
from search_dialogue import SearchDialogue
from action_policy import Action

URL='https://example.org/'
REQUEST='/rechercher Quel prix Louvre ?'


_desktop_root=None


@pytest.fixture(scope='module',autouse=True)
def desktop_interpreter(validation_desktop_root):
    # One Tcl interpreter, as in the real desktop app. Each case still builds
    # all real widgets in its own window; destroying it removes its callbacks.
    global _desktop_root
    _desktop_root=validation_desktop_root
    yield
    _desktop_root=None
    gc.collect()


def run_loop(texts,reader,*,route_side_effect=None,planner=None):
    previous_directory=os.getcwd()
    window=tk.Toplevel(_desktop_root);window.withdraw()
    session=Mock(model_spec={'name':'validation model'})
    session.ask.return_value=('{"decision":"execute"}',0,0)
    voice=Mock(interruption_epoch=0);voice.speak.return_value=True
    hearing=Mock();memory=Mock();memory.answer.return_value=('Conversation fictive',False)
    # Match the real stop-listener context without opening any microphone.
    from contextlib import nullcontext
    hearing.stop_only.side_effect=lambda *args,**kwargs:nullcontext()
    initiative=Mock(mode='quiet',public_boundary=False);initiative.has_ready.return_value=False
    incoming=iter(texts);controller=SearchDialogue(session,reader=reader,**({"planner":planner} if planner else {}))
    def command(operation,**kwargs):
        if operation=='listen':
            text=next(incoming,None)
            if text is None:app.stop.set();return {'status':'idle'}
            return {'status':'transcribed','accepted':True,'text':text,'cleaned':text}
        return {}
    hearing.command.side_effect=command
    try:
        with ExitStack() as stack:
            for name in ('Library','PublicMemory','Thoughts','Subtitles'):
                stack.enter_context(patch('alice_desktop.'+name))
            for name,value in [('Session',session),('Memory',memory),('Voice',voice),
                               ('Hearing',hearing),('DesktopInitiative',initiative),('Observation',MagicMock())]:
                stack.enter_context(patch('alice_desktop.'+name,return_value=value))
            stack.enter_context(patch('search_dialogue.SearchDialogue',return_value=controller))
            router=stack.enter_context(patch('intent_router.route',return_value=(Action('chat'),'Bonjour')))
            if route_side_effect:router.side_effect=lambda *args:route_side_effect(voice,*args)
            with patch('alice_desktop.threading.Thread'):
                app=alice_desktop.Application(window)
            app.confirm=Mock(side_effect=AssertionError('button not expected'))
            app.run()
            return {'spoken':[call.args[0] for call in voice.speak.call_args_list],
                'memory':memory,'router':router,'confirm':app.confirm,'controller':controller,
                'events':list(app.events.queue),
                'voice':voice,'finished':app.finished.is_set()}
    finally:
        window.destroy()
        os.chdir(previous_directory)


def test_search_then_conversation_keeps_page_out_of_memory_and_router():
    reader=Mock(return_value={'status':'found','reply':'PAGE_PRIVATE_SENTINEL',
        'url':URL+'prices','visited':[URL,URL+'prices'],'partial':True})
    result=run_loop([REQUEST,'Bonjour'],reader)
    reader.assert_called_once();result['confirm'].assert_not_called()
    assert 'PAGE_PRIVATE_SENTINEL' in result['spoken']
    result['memory'].answer.assert_called_once();result['router'].assert_called_once()
    assert 'PAGE_PRIVATE_SENTINEL' not in repr(result['memory'].answer.call_args)
    assert 'PAGE_PRIVATE_SENTINEL' not in repr(result['router'].call_args)
    assert not result['controller'].turns and result['finished']


def test_interruption_during_read_never_speaks_returned_page():
    def reader(session,*args,**kwargs):
        session.voice.interruption_epoch+=1
        return {'status':'found','reply':'STALE_PAGE_SENTINEL'}
    result=run_loop([REQUEST],Mock(side_effect=reader))
    assert not result['spoken'] and not result['controller'].turns
    result['memory'].answer.assert_not_called();result['router'].assert_not_called()


def test_interruption_during_router_blocks_fallback_search_controller():
    def routed(voice,*args):
        voice.interruption_epoch+=1
        return Action('web_search','irrelevant'),''
    reader=Mock()
    result=run_loop(['Voici une formulation non reconnue'],reader,route_side_effect=routed)
    reader.assert_not_called();result['confirm'].assert_not_called()
    assert not result['spoken'] and not result['controller'].turns


def test_router_fallback_passes_original_and_never_opens_memory():
    original='Voici une formulation non reconnue'
    def routed(voice,*args):return Action('web_search','MODEL_REWRITE_SENTINEL'),''
    reader=Mock(return_value={'status':'found','reply':'Extrait verifie'})
    result=run_loop([original],reader,route_side_effect=routed)
    assert reader.call_args.args[1]==original
    assert reader.call_args.kwargs['source']=='voice'
    result['memory'].answer.assert_not_called()
    assert result['spoken']==['Extrait verifie']


@pytest.mark.parametrize('boundary',['Bonjour','/initiative calme','/reset'])
def test_pending_request_cannot_resume_after_unrelated_or_mode_turn(boundary):
    planner=Mock(return_value={'status':'clarify'})
    reader=Mock()
    result=run_loop([REQUEST,boundary,'La question est Quel prix ?'],reader,planner=planner)
    assert planner.call_count==1
    reader.assert_not_called()
    assert not result['controller'].turns


def test_new_search_cancels_notes_and_links():
    with patch('notes_dialogue.NotesDialogue.cancel') as notes_cancel, patch('link_dialogue.LinkDialogue.cancel') as links_cancel:
        result=run_loop([REQUEST],Mock(return_value={'status':'found','reply':'Extrait'}))
    assert notes_cancel.call_count>=1 and links_cancel.call_count>=1
    result['router'].assert_not_called();result['memory'].answer.assert_not_called()


def test_link_request_clears_pending_search_before_handling_link():
    planner=Mock(return_value={'status':'clarify'});reader=Mock()
    with patch('link_dialogue.LinkDialogue.handle',return_value={'status':'read','reply':'Extrait fictif'}):
        result=run_loop([REQUEST,f'/suivre {URL} | Tarifs | Quel prix ?','La question est Quel prix ?'],reader,planner=planner)
    assert planner.call_count==1
    reader.assert_not_called()
    assert not result['controller'].turns
