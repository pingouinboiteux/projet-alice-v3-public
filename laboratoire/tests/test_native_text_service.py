from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_task_permission import NativeTaskPermission
from native_text_service import run_authorized_text
from native_typing_context import TabbedTypingContext


TASK={'window':{'hwnd':1,'pid':2,'created':3},'target':'field','text':'validation_texte'}


def setup():
    permissions=NativeTaskPermission()
    review=permissions.propose(TASK,source='text')
    permit=permissions.approve(review['ticket'],True,source='text')
    state={'window':TASK['window'],'available':True,'foreground':True,'truncated':False,
        'geometry':[0,0,400,300], 'elements':[{'id':'field','name':'Texte','rect':[10,10,200,30],
        'value':'','visible':True,'enabled':True,'focused':True,'password':False}]}
    observer=Mock();observer.read.side_effect=lambda:deepcopy(state)
    transport=Mock()
    def type_text(text,*,preflight,cancelled):
        preflight()
        assert not cancelled()
        state['elements'][0]['value']=text
    transport.type_text.side_effect=type_text
    return permissions,permit,observer,transport,state


def test_authorized_text_runs_real_guard_controller_and_verifier():
    p,permit,o,t,s=setup()
    with patch('native_action_planner.choose',return_value={'op':'type','target':'field','text':TASK['text']}):
        result=run_authorized_text(Mock(),o,t,p,permit,TASK)
    assert result['verified'] and result['status']=='complete'
    assert s['elements'][0]['value']==TASK['text']
    with pytest.raises(ValueError):p.claim(permit,TASK)


def test_wrong_task_cannot_even_read_window():
    p,permit,o,t,s=setup()
    with pytest.raises(ValueError):
        run_authorized_text(Mock(),o,t,p,permit,dict(TASK,text='changed'))
    o.read.assert_not_called();t.type_text.assert_not_called()


def test_cancellation_after_planning_prevents_typing():
    p,permit,o,t,s=setup()
    def choose(*args):
        p.cancel()
        return {'op':'type','target':'field','text':TASK['text']}
    with patch('native_action_planner.choose',side_effect=choose):
        result=run_authorized_text(Mock(),o,t,p,permit,TASK)
    assert not result['verified']
    t.type_text.assert_not_called()


def test_finishing_old_lease_preserves_new_proposal():
    p,permit,o,t,s=setup();lease=p.claim(permit,TASK)
    review=p.propose(dict(TASK,text='new'),source='voice')
    p.finish(lease)
    new=p.approve(review['ticket'],True,source='voice')
    assert p.active(p.claim(new,dict(TASK,text='new')))


def document_context(state):
    state['elements'][0].update(type='ControlType.Document',parent_id='root')
    state['elements'].extend([
        {'id':'root','parent_id':None,'type':'ControlType.Window','name':'Document',
         'value':None,'rect':[0,0,400,300],'visible':True,'enabled':True,'password':False,'focused':False},
        {'id':'tab','parent_id':'root','type':'ControlType.TabItem','name':'Document',
         'value':None,'rect':[0,0,120,20],'selected':True,'visible':True,'enabled':True,
         'password':False,'focused':False}])
    return TabbedTypingContext(state,'field')


def test_changed_document_with_identical_text_is_not_already_completed():
    p,permit,o,t,s=setup()
    context=document_context(s)
    s['elements'][0]['value']=TASK['text']
    s['elements'][-1]['id']='another_tab'
    result=run_authorized_text(Mock(),o,t,p,permit,TASK,typing_context=context)
    assert not result['verified']
    t.type_text.assert_not_called()
    t.click.assert_not_called()


def test_changed_document_after_last_input_cannot_pass_final_verification():
    p,permit,o,t,s=setup()
    context=document_context(s)
    def write(text,*,preflight,cancelled):
        preflight()
        s['elements'][0]['value']=text
        # A tab switch reuses the editor and happens to expose the same text.
        s['elements'][-1]['id']='another_tab'
    t.type_text.side_effect=write
    with patch('native_action_planner.choose',return_value={'op':'type','target':'field','text':TASK['text']}):
        result=run_authorized_text(Mock(),o,t,p,permit,TASK,typing_context=context)
    assert not result['verified']
    assert result['status']=='uncertain'
    assert t.type_text.call_count==1  # No automatic retry after possible input.
