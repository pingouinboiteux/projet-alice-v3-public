from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_target_selection import select_window,select_text_control


WINDOW={'window':{'hwnd':1,'pid':2,'created':3},'title':'Sans titre - Bloc-notes',
        'process_name':'notepad.exe','visible':True}


def test_window_name_matches_only_allowed_process():
    malicious=dict(WINDOW,process_name='brave.exe')
    selected=select_window([malicious,WINDOW],'Bloc-notes',allowed_processes=['notepad.exe'])
    assert selected==WINDOW
    selected['window']['pid']=99
    assert WINDOW['window']['pid']==2


@pytest.mark.parametrize('candidates',[[],[WINDOW,WINDOW],[dict(WINDOW,visible=False)]])
def test_window_missing_hidden_or_ambiguous(candidates):
    with pytest.raises(ValueError): select_window(candidates,'Bloc-notes',allowed_processes=['notepad.exe'])


def test_partial_window_title_not_enough():
    with pytest.raises(ValueError):select_window([WINDOW],'Sans titre',allowed_processes=['notepad.exe'])


def scene():
    return {'truncated':False,'foreground':True,'available':True,'elements':[
        {'id':'edit','type':'ControlType.Edit','editable':True,'password':False,
         'visible':True,'enabled':True,'value':''}]}


def test_unique_empty_or_already_correct_field():
    state=scene()
    assert select_text_control(state,'hello')=='edit'
    state['elements'][0]['value']='hello'
    assert select_text_control(state,'hello')=='edit'


@pytest.mark.parametrize('field,value',[('editable',False),('password',True),('visible',False),
                                     ('enabled',False),('value','existing')])
def test_unsupported_or_existing_field_not_selected(field,value):
    state=scene();state['elements'][0][field]=value
    with pytest.raises(ValueError): select_text_control(state,'hello')


def test_focused_field_does_not_override_ambiguity():
    state=scene();state['elements'][0]['focused']=True
    state['elements'].append(dict(state['elements'][0],id='search',focused=False))
    with pytest.raises(ValueError):select_text_control(state,'hello')
