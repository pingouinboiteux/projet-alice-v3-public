import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from observer_tiddlywiki import parse_tid,validate_note_action

def observation():
    return {'elements':[{'id':x,'enabled':True} for x in ('title','body','save')]}

def test_disk_parser_keeps_exact_body():
    assert parse_tid('title: validation_note\ntype: text/vnd.tiddlywiki\n\n<b>été</b>\n  x\n')=={
        'title':'validation_note','body':'<b>été</b>\n  x\n'}

def test_drafts_not_reported_as_persisted_note():
    assert parse_tid('title: draft\ndraft.of: x\n\ntext') is None

@pytest.mark.parametrize('action',[
    {'op':'click','target':'delete'}, {'op':'fill','target':'path','value':'x'},
    {'op':'fill','target':'title','value':'$:/config/x'},
    {'op':'fill','target':'title','value':'x\ny'},
    {'op':'fill','target':'body','value':True},
    {'op':'fill','target':'body','value':'x','selector':'body'},
])
def test_invalid_commands_are_rejected(action):
    with pytest.raises(ValueError):validate_note_action(action,observation())

def test_multiline_literal_body_and_commit_allowed():
    validate_note_action({'op':'fill','target':'body','value':'<b>été</b>\n  x'},observation())
    validate_note_action({'op':'click','target':'save'},observation())

def test_duplicate_target_refused():
    snap=observation();snap['elements'].append({'id':'save','enabled':True})
    with pytest.raises(ValueError):validate_note_action({'op':'click','target':'save'},snap)
