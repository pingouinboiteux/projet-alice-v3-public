"""Ordinary desktop loop with synthetic services only, no personal data."""
from contextlib import ExitStack
import gc
import os
import tkinter as tk
from unittest.mock import Mock,MagicMock,patch
import pytest
import alice_desktop
from link_dialogue import LinkDialogue
from action_policy import Action

URL='https://example.org/'
REQUEST=f'/suivre {URL} | Tarifs | Quel prix ?'


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


def run_loop(texts,reader,*,route_side_effect=None):
    previous_directory=os.getcwd()
    window=tk.Toplevel(_desktop_root);window.withdraw()
    session=Mock(model_spec={'name':'validation model'})
    voice=Mock(interruption_epoch=0);voice.speak.return_value=True
    hearing=Mock();memory=Mock();memory.answer.return_value=('Conversation fictive',False)
    initiative=Mock(mode='quiet');initiative.has_ready.return_value=False
    incoming=iter(texts);controller=LinkDialogue(session,reader=reader)
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
            stack.enter_context(patch('link_dialogue.LinkDialogue',return_value=controller))
            router=stack.enter_context(patch('intent_router.route',return_value=(Action('chat'),'Bonjour')))
            if route_side_effect:router.side_effect=lambda *args:route_side_effect(voice,*args)
            with patch('alice_desktop.threading.Thread'):
                app=alice_desktop.Application(window)
            app.confirm=Mock(side_effect=AssertionError('button not expected'))
            app.run()
            return {'spoken':[call.args[0] for call in voice.speak.call_args_list],
                'memory':memory,'router':router,'confirm':app.confirm,'controller':controller,
                'voice':voice,'finished':app.finished.is_set()}
    finally:
        window.destroy()
        os.chdir(previous_directory)


def test_link_then_conversation_keeps_page_out_of_memory_and_router():
    reader=Mock(return_value={'status':'read','reply':'PAGE_PRIVATE_SENTINEL',
        'url':URL+'prices','from_url':URL,'partial':True})
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
        return {'status':'read','reply':'STALE_PAGE_SENTINEL'}
    result=run_loop([REQUEST],Mock(side_effect=reader))
    assert not result['spoken'] and not result['controller'].turns
    result['memory'].answer.assert_not_called();result['router'].assert_not_called()


def test_interruption_during_router_blocks_fallback_link_controller():
    def routed(voice,*args):
        voice.interruption_epoch+=1
        return Action('web_follow','irrelevant'),''
    reader=Mock()
    result=run_loop(['Voici une formulation non reconnue'],reader,route_side_effect=routed)
    reader.assert_not_called();result['confirm'].assert_not_called()
    assert not result['spoken'] and not result['controller'].turns
