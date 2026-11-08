"""Synthetic pictures only. No host capture, model, microphone or personal memory."""
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screen_capture import Monitor
from screen_observer import ScreenObserver,command
from screen_model import analyze
from screen_events import DeathEvents
from screen_ocr import death_banner

MONITOR=Monitor('validation_screen',(0,0,640,480),True)
VALUE={'description':'Une erreur fictive est affichee.','reaction':'Une erreur est visible.','notable':True,'uncertain':False}

@pytest.fixture
def observer():
    clock=Mock(return_value=100.)
    capture=Mock(side_effect=lambda _:Image.new('RGB',(640,480),'white'))
    session=SimpleNamespace(vision_enabled=True)
    obj=ScreenObserver(session,Mock(),capturer=capture,inventory=lambda:[MONITOR],reader=Mock(return_value=VALUE.copy()),clock=clock,game=lambda _:False)
    obj.target=MONITOR
    yield obj
    obj.close()

@pytest.mark.parametrize('text,action',[('Alice, regarde mon écran','regarde'),('surveille mon écran 2','surveille'),('/ecran stop','stop'),('coupe la vision','stop'),('/ecran nimportequoi','help')])
def test_commands(text,action):assert command(text)[0]==action

def test_external_source_cannot_even_list(observer):
    observer.inventory=Mock()
    with pytest.raises(PermissionError):observer.handle('/ecran liste','discord')
    observer.inventory.assert_not_called()

def test_stopped_never_captures(observer):
    observer.stop();observer.tick();observer.capture.assert_not_called()

def test_busy_never_captures(observer):
    observer.busy=lambda:True;observer.tick();observer.capture.assert_not_called()

def test_unchanged_screen_not_inferred_or_repeated(observer):
    observer.tick();observer.clock.return_value=125;observer.tick()
    assert observer.reader.call_count==1 and observer.has_ready()

def test_stop_during_inference_discards_result_and_context(observer):
    def read(*a,**k):observer.stop();return VALUE.copy()
    observer.reader.side_effect=read;observer.tick()
    assert not observer.has_ready();assert observer.previous==''

def test_local_input_during_inference_discards_result(observer):
    def read(*a,**k):observer.busy=lambda:True;return VALUE.copy()
    observer.reader.side_effect=read;observer.tick();assert not observer.has_ready()

@pytest.mark.parametrize('field,value',[('notable',False),('uncertain',True),('reaction','')])
def test_uninteresting_or_uncertain_never_interrupts(observer,field,value):
    observer.reader.return_value={**VALUE,field:value};observer.tick();assert not observer.has_ready()

def test_cooldown_between_different_reactions(observer):
    observer.tick();first=observer.take();observer.clock.return_value=125
    observer.capture.side_effect=lambda _:Image.new('RGB',(640,480),'black')
    observer.reader.return_value={**VALUE,'reaction':'Autre constat'}
    observer.tick();assert first is not None and not observer.has_ready()

def test_on_demand_and_no_persistent_context(observer):
    answer=observer.handle('/ecran regarde 1 | que vois-tu ?','text')
    assert 'erreur' in answer and observer.previous==''

def test_absent_screen_never_captures(observer):
    assert 'absent' in observer.handle('/ecran regarde 2','text')
    observer.capture.assert_not_called()

def test_no_vision_returns_help_without_capture(observer):
    observer.session.vision_enabled=False
    assert 'Alice-vision.bat' in observer.handle('/ecran regarde','text')
    observer.capture.assert_not_called()

def test_old_result_rejected(observer):
    def read(*a,**k):observer.clock.return_value=146;return VALUE.copy()
    observer.reader.side_effect=read;observer.tick();assert not observer.has_ready()

def test_visual_transport_is_separate_and_schema_checked():
    session=SimpleNamespace(vision_enabled=True,inference_lock=threading.RLock(),request=Mock(return_value={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(VALUE)}}]}))
    with Image.new('RGB',(200,100),'white') as image:
        assert analyze(session,image,'validation_question')==VALUE
        payload=session.request.call_args.args[1]
        assert len(payload['messages'])==2 and 'tools' not in payload
        assert payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        session.request.return_value['choices'][0]['message']['content']='{"command":"powershell"}'
        with pytest.raises(ValueError):analyze(session,image,'validation_question')

def test_passive_does_not_wait_for_busy_model():
    lock=Mock();lock.acquire.return_value=False
    session=SimpleNamespace(vision_enabled=True,inference_lock=lock,request=Mock())
    with Image.new('RGB',(20,20)) as image:assert analyze(session,image,'q',passive=True) is None
    session.request.assert_not_called()

def test_cancelled_model_response_not_delivered():
    cancelled=[False]
    def request(*a,**kw):cancelled[0]=True;return {}
    session=SimpleNamespace(vision_enabled=True,inference_lock=threading.RLock(),request=request)
    with Image.new('RGB',(20,20)) as image:assert analyze(session,image,'q',cancelled=lambda:cancelled[0]) is None


def test_same_banner_is_not_multiple_deaths():
    events=DeathEvents()
    for now in range(0,150,5):assert not events.update(True,now)
    assert len(events.events)==1


def test_three_distinct_deaths_in_short_window():
    events=DeathEvents()
    assert not events.update(True,0)
    events.update(False,5);events.update(False,10)
    assert not events.update(True,30)
    events.update(False,35);events.update(False,40)
    assert events.update(True,60)
    assert not events.update(True,65)
    events.update(False,250);events.update(False,255)
    assert not events.update(True,260) and len(events.events)==1


def test_failed_ocr_does_not_rearm_death_counter():
    events=DeathEvents();events.update(True,0)
    events.update(None,5);events.update(None,10);events.update(True,30)
    assert len(events.events)==1


@pytest.mark.parametrize('text,expected',[('VOUS ÊTES MORT',True),('Vous avez été tué',True),('YOU DIED',True),('Vous êtes vivant',False),('mort',False)])
def test_banner_phrase_only(text,expected):assert death_banner(text)==expected


def test_pending_reaction_expires_and_stop_removes_it(observer):
    observer.tick();assert observer.has_ready()
    observer.clock.return_value=131;assert not observer.has_ready()
    observer.pending=(observer.generation,131,'validation');observer.stop()
    assert not observer.has_ready()


def test_sarcasm_only_after_three_events_in_known_game(observer):
    observer.game=lambda _:True;observer.ocr=Mock(return_value=True)
    observer.deaths.events.extend([40,70]);observer.deaths.present=False
    observer.tick()
    assert 'sarcastique' in observer.reader.call_args.args[2]


def test_no_ocr_on_non_game_window(observer):
    observer.ocr=Mock();observer.tick();observer.ocr.assert_not_called()


def test_requested_inspection_cancels_queued_sarcasm(observer):
    observer.tick();assert observer.has_ready()
    observer.handle('/ecran regarde','text')
    assert not observer.has_ready()


def test_question_can_follow_natural_screen_request():
    action,index,question=command('Alice regarde mon écran 2, combien de secondes restent ?')
    assert action=='regarde' and index=='2' and 'secondes' in question
