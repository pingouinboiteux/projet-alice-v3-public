"""Synthetic files and mocked UI only; no personal wiki or actual browser."""
from pathlib import Path
import io
import sys
import tempfile
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from observer_tiddlywiki import TiddlyWikiApp, ROOT, fingerprint, parse_tid

@pytest.fixture
def app():
    base=ROOT/'data/validation';base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validation_note_operations_',dir=base) as temporary:
        value=TiddlyWikiApp(lambda:None,clock=lambda:0)
        value.wiki=Path(temporary)/'wiki';(value.wiki/'tiddlers').mkdir(parents=True)
        value.page=Mock()
        value.page.locator.return_value.count.return_value=0
        yield value
        value._http.close()

def write(app,name,title,body='Text',extra=''):
    path=app.wiki/'tiddlers'/name
    path.write_text('title: '+title+'\n'+extra+'\n'+body,encoding='utf-8')
    return path

def test_list_titles_ignores_system_and_drafts_without_reading_bodies(app):
    write(app,'b.tid','Beta','x'*100000)
    write(app,'a.tid','Alpha')
    write(app,'sys.tid','$:/config/Test','x'*100000)
    write(app,'draft.tid','Draft',extra='draft.title: Beta\n')
    assert app.list_notes()=={'titles':['Alpha','Beta'],'truncated':False}
    assert app.list_notes(1)['truncated']
    app.page.assert_not_called()

def test_header_reader_stops_before_body():
    stream=io.StringIO('title: Validation\ntype: text/plain\n\nBODY')
    assert TiddlyWikiApp._read_header(stream)=={'title':'Validation','type':'text/plain'}
    assert stream.read()=='BODY'

def test_header_only_empty_tiddler_does_not_block_other_notes(app):
    (app.wiki/'tiddlers/empty.tid').write_text('title: $:/StoryList\nlist: ',encoding='utf-8')
    (app.wiki/'tiddlers/user.tid').write_text('title: Empty',encoding='utf-8')
    write(app,'normal.tid','Normal')
    assert app.list_notes()=={'titles':['Empty','Normal'],'truncated':False}
    assert app._disk_note('Empty')=={'title':'Empty','body':''}

@pytest.mark.parametrize('limit',[0,51,True,'2'])
def test_list_limit_is_bounded(app,limit):
    with pytest.raises(ValueError):app.list_notes(limit)

@pytest.mark.parametrize('title',['$:/config/Test','', 'x\ny','x'*81])
def test_read_system_or_invalid_title_is_rejected_before_disk(app,title):
    app._disk_note=Mock()
    with pytest.raises(ValueError):app.read_note(title)
    app._disk_note.assert_not_called()

def test_read_note_requires_disk_and_ui_and_returns_detached_data(app):
    write(app,'note.tid','Validation','Garder  deux espaces\nété')
    app.verify_persisted=Mock(return_value=True)
    assert app.read_note('Missing') is None
    target={'title':'Validation','body':'Garder  deux espaces\nété'}
    assert app.read_note('Validation')==target
    app.verify_persisted.assert_called_once_with(target)
    app.verify_persisted.return_value=False
    with pytest.raises(RuntimeError,match='note_changed'):app.read_note('Validation')

def test_read_detects_change_during_ui_verification(app):
    path=write(app,'note.tid','Validation','Before')
    def verify(expected):
        path.write_text('title: Validation\n\nChanged',encoding='utf-8')
        return True
    app.verify_persisted=verify
    with pytest.raises(RuntimeError,match='note_changed'):app.read_note('Validation')

def test_ambiguous_disk_title_and_oversized_body_fail_closed(app):
    write(app,'one.tid','Same','First');other=write(app,'two.tid','Same','Second')
    with pytest.raises(RuntimeError,match='Ambiguous'):app._disk_note('Same')
    other.unlink()
    write(app,'big.tid','Big','x'*4097)
    with pytest.raises(RuntimeError,match='limit'):app._disk_note('Big')

def test_prepare_edit_checks_disk_ui_and_binds_original(app):
    original={'title':'Validation','body':'Before'}
    write(app,'note.tid',**{'title':'Validation','body':'Before'})
    app._open_note_editor=Mock(return_value=dict(original));app.observe=Mock(return_value={'snapshot':True})
    assert app.prepare_edit(original)=={'snapshot':True}
    original['body']='Mutated caller'
    assert app._editing_original=={'title':'Validation','body':'Before'}
    assert app._saved is None

def test_prepare_edit_refuses_changed_note_before_or_during_open(app):
    expected={'title':'Validation','body':'Before'}
    path=write(app,'note.tid','Validation','Changed')
    app._open_note_editor=Mock()
    with pytest.raises(RuntimeError,match='note_changed'):app.prepare_edit(expected)
    app._open_note_editor.assert_not_called()
    path.write_text('title: Validation\n\nBefore',encoding='utf-8')
    app._open_note_editor.return_value={'title':'Validation','body':'Other'}
    with pytest.raises(RuntimeError,match='note_changed'):app.prepare_edit(expected)

def prepare_save(app,title='Validation'):
    before={'elements':[{'id':'title','enabled':True,'value':title},
                        {'id':'body','enabled':True,'value':'After'},
                        {'id':'save','enabled':True,'value':None}], 'saved':None}
    snapshot={**before,'observed_at':0}
    app._issued=(fingerprint(snapshot),snapshot)
    app._read=Mock(return_value=before);app.observe=Mock(return_value=snapshot)
    app._editing_original={'title':'Validation','body':'Before'}
    return snapshot

def test_disk_change_after_preview_prevents_save_click(app):
    write(app,'note.tid','Validation','Changed elsewhere')
    snapshot=prepare_save(app)
    result=app.act({'op':'click','target':'save'},snapshot)
    assert result['reason']=='note_changed' and not result['ok']
    app.page.locator.assert_not_called()


def test_backup_failure_prevents_note_replacement(app,monkeypatch):
    write(app,'note.tid','Validation','Before')
    snapshot=prepare_save(app)
    def fail(*args):raise OSError('validation_disk_full')
    monkeypatch.setattr('note_versions.remember',fail)
    with pytest.raises(OSError):app.act({'op':'click','target':'save'},snapshot)
    app.page.locator.assert_not_called()

def test_edit_cannot_rename_note(app):
    snapshot=prepare_save(app,'Other')
    app.title_exists=Mock(return_value=False)
    result=app.act({'op':'click','target':'save'},snapshot)
    assert result['reason']=='note_title_changed'
    app.page.locator.assert_not_called()

def test_parser_excludes_system_and_both_draft_fields():
    assert parse_tid('title: $:/config/State\n\nSecret') is None
    assert parse_tid('title: Draft\ndraft.title: Foo\n\nDraft') is None
