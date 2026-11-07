from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_text_dialogue import NativeTextDialogue


TEXT='Ecris dans le bloc-notes le texte : validation_texte'
WINDOW={'hwnd':1,'pid':2,'created':3}


def setup():
    inventory=Mock(return_value=[{'window':WINDOW,'title':'Notes','process_name':'notepad.exe','visible':True}])
    observer=Mock()
    observer.read.return_value={'window':WINDOW,'foreground':True,'available':True,'truncated':False,
        'elements':[{'id':'field','type':'ControlType.Edit','editable':True,'password':False,
                     'visible':True,'enabled':True,'value':''}]}
    cleanup=Mock()
    @contextmanager
    def factory(window,*,cancelled):
        try: yield SimpleNamespace(observer=observer,transport=Mock())
        finally: cleanup()
    execute=Mock(return_value={'status':'complete','verified':True})
    controller=NativeTextDialogue(Mock(),inventory,factory,allowed_processes=['notepad.exe'],executor=execute)
    return controller,inventory,observer,execute,cleanup


def test_literal_request_reaches_exact_task_and_cleanup():
    c,i,o,e,cleanup=setup()
    assert c.handle(TEXT,'voice')['verified']
    args=e.call_args.args
    task=args[-1]
    assert task=={'window':WINDOW,'target':'field','text':'validation_texte'}
    with pytest.raises(ValueError):args[3].claim(args[4],task)
    cleanup.assert_called_once()


def test_example_does_not_read_pc():
    c,i,o,e,cleanup=setup()
    assert c.handle('Si je dis '+TEXT,'text')['status']=='not_handled'
    i.assert_not_called();o.read.assert_not_called();e.assert_not_called()


@pytest.mark.parametrize('source',['twitch','discord','page','model'])
def test_external_source_cannot_touch_inventory(source):
    c,i,o,e,cleanup=setup()
    with pytest.raises(ValueError):c.handle(TEXT,source)
    i.assert_not_called()


def test_two_windows_never_pick_first():
    c,i,o,e,cleanup=setup();i.return_value*=2
    assert not c.handle(TEXT,'text')['verified']
    o.read.assert_not_called();e.assert_not_called()


def test_changed_window_after_binding_stops():
    c,i,o,e,cleanup=setup();o.read.return_value['window']=dict(WINDOW,pid=99)
    assert not c.handle(TEXT,'text')['verified']
    e.assert_not_called();cleanup.assert_called_once()


def test_existing_content_not_overwritten():
    c,i,o,e,cleanup=setup();o.read.return_value['elements'][0]['value']='existing'
    assert not c.handle(TEXT,'voice')['verified']
    e.assert_not_called();cleanup.assert_called_once()


def test_window_title_change_after_observation_stops():
    c,i,o,e,cleanup=setup()
    original=i.return_value
    i.side_effect=[original,[dict(original[0],title='Different document')]]
    assert not c.handle(TEXT,'voice')['verified']
    e.assert_not_called();cleanup.assert_called_once()


def test_cancel_before_work():
    c,i,o,e,cleanup=setup()
    assert not c.handle(TEXT,'voice',cancelled=lambda:True)['verified']
    i.assert_not_called();e.assert_not_called()
