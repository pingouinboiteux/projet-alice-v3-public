"""Persistent storage tests on explicit validation directories, no real notes."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from notes_storage import NotesStorage, ROOT
from observer_tiddlywiki import TiddlyWikiApp, SAVE
from observer_browser import BrowserDemo, fingerprint


@pytest.fixture
def folder():
    base=ROOT/'data/validation'
    base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validation_notes_storage_',dir=base) as name:
        yield Path(name)


def test_validation_storage_is_lazy_and_constrained(folder):
    path=folder/'wiki'
    storage=NotesStorage.validation(path)
    assert not path.exists()
    assert not storage.is_personal
    for invalid in (ROOT/'data/notes/wiki',ROOT/'data/validation/wiki',folder/'..'/'wiki'):
        with pytest.raises(ValueError):NotesStorage.validation(invalid)


def test_reopen_preserves_data_and_duplicate_acquire_is_exclusive(folder):
    path=folder/'wiki'
    first=NotesStorage.validation(path);second=NotesStorage.validation(path)
    assert first.acquire()==path
    (path/'tiddlywiki.info').write_text('{}',encoding='utf-8')
    (path/'note.tid').write_text('title: validation_note\n\nOriginal',encoding='utf-8')
    with pytest.raises(OSError):second.acquire()
    # A failed second acquisition must not release the first owner's lock.
    with pytest.raises(OSError):NotesStorage.validation(path).acquire()
    first.release();first.release()
    assert second.acquire()==path
    assert (path/'note.tid').read_text(encoding='utf-8').endswith('Original')
    second.release()


def test_unrecognized_directory_refused_without_overwriting(folder):
    path=folder/'wiki';path.mkdir()
    (path/'keep.txt').write_text('validation original')
    storage=NotesStorage.validation(path)
    with pytest.raises(ValueError,match='unrecognized'):storage.acquire()
    assert (path/'keep.txt').read_text()=='validation original'
    assert storage._lock_file is None


def test_validation_rejects_linked_directory(folder):
    actual=folder/'actual';actual.mkdir()
    link=folder/'linked'
    try:link.symlink_to(actual,target_is_directory=True)
    except OSError:pytest.skip('Symlink creation unavailable')
    with pytest.raises(ValueError,match='linked'):NotesStorage.validation(link/'wiki')


def test_validation_rejects_windows_reparse_attribute_without_link_privilege(folder,monkeypatch):
    import stat
    from types import SimpleNamespace
    path=folder/'redirected';path.mkdir()
    original=Path.lstat
    def attributes(value,*args,**kwargs):
        result=original(value,*args,**kwargs)
        return SimpleNamespace(st_mode=result.st_mode,st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT) if value==path else result
    monkeypatch.setattr(Path,'lstat',attributes)
    with pytest.raises(ValueError,match='linked'):NotesStorage.validation(path/'wiki')


def test_storage_cannot_be_shared_by_two_live_apps(folder,monkeypatch):
    storage=NotesStorage.validation(folder/'wiki');storage.acquire()
    (storage.directory/'tiddlywiki.info').write_text('{}')
    app=TiddlyWikiApp(lambda:None,storage=storage)
    # close on an app that never acquired the shared object cannot unlock it.
    app.close()
    with pytest.raises(OSError):NotesStorage.validation(folder/'wiki').acquire()
    storage.release()


@pytest.mark.parametrize('original',[None, {'title':'Other','body':'Old'}])
def test_creation_or_rename_collision_does_not_click_save(original):
    app=TiddlyWikiApp(lambda:None,clock=lambda:0)
    before={'elements':[{'id':'title','value':'Existing','enabled':True},
        {'id':'body','value':'Replacement','enabled':True},{'id':'save','value':None,'enabled':True}],
        'saved':None}
    snapshot={**before,'observed_at':0}
    app._issued=(fingerprint(snapshot),snapshot)
    app._read=Mock(return_value=before);app.observe=Mock(return_value=snapshot)
    app.title_exists=Mock(return_value=True);app.page=Mock()
    app._editing_original=original
    result=app.act({'op':'click','target':'save'},snapshot)
    assert result['reason']=='note_title_exists' and not result['verified']
    app.page.locator.assert_not_called()


def test_reopen_skips_initialization_and_credentials_are_temporary(folder,monkeypatch):
    import observer_tiddlywiki as module
    path=folder/'wiki';path.mkdir()
    (path/'tiddlywiki.info').write_text('{}')
    package=folder/'package';package.mkdir()
    (package/'package.json').write_text(json.dumps({'version':'5.4.1'}))
    (package/'core/wiki/config').mkdir(parents=True)
    (package/'core/wiki/config/SyncFilter.tid').write_text('title: $:/config/SyncFilter\n\n[is[tiddler]]\n')
    monkeypatch.setattr(module,'PACKAGE',package)
    monkeypatch.setattr(module.shutil,'which',lambda name:'node')
    process=Mock();state=[None]
    process.poll.side_effect=lambda:state[0]
    process.terminate.side_effect=lambda:state.__setitem__(0,0)
    popen=Mock(return_value=process);monkeypatch.setattr(module.subprocess,'Popen',popen)
    monkeypatch.setattr(BrowserDemo,'start',lambda self:self)
    app=TiddlyWikiApp(lambda:None,storage=NotesStorage.validation(path))
    app.context=Mock();app.page=Mock();app._diagnose=Mock()
    app._http.get=Mock(return_value=Mock(status_code=200))
    try:
        app.start()
        assert popen.call_count==1
        command=popen.call_args.args[0]
        assert '--listen' in command and '--init' not in command
        value=next(arg.split('=',1)[1] for arg in command if arg.startswith('credentials='))
        credentials=(path/value).resolve()
        assert credentials.parent==Path(app._wiki_temp.name).resolve()
        assert not credentials.is_relative_to(path)
        assert credentials.exists()
    finally:app.close()
    assert path.exists() and (path/'tiddlywiki.info').exists()
    assert not credentials.exists()
    reopened=NotesStorage.validation(path);reopened.acquire();reopened.release()


def test_persistent_sync_excludes_drafts_and_refuses_unrecognized_override(folder,monkeypatch):
    import observer_tiddlywiki as module
    package=folder/'package';(package/'core/wiki/config').mkdir(parents=True)
    (package/'core/wiki/config/SyncFilter.tid').write_text('title: $:/config/SyncFilter\n\n[is[tiddler]]\n')
    monkeypatch.setattr(module,'PACKAGE',package)
    app=TiddlyWikiApp(lambda:None,storage=NotesStorage.validation(folder/'wiki'))
    app.wiki=app.storage.acquire()
    try:
        app._configure_persistent_sync()
        config=app.wiki/'tiddlers/alice-sync-filter.tid'
        assert config.read_text().endswith('-[has[draft.of]] -[has[draft.title]]\n')
        app._configure_persistent_sync()
        config.write_text('Unexpected user configuration')
        with pytest.raises(RuntimeError,match='configuration changed'):app._configure_persistent_sync()
        assert config.read_text()=='Unexpected user configuration'
    finally:app.storage.release()


def test_title_exists_checks_disk_before_browser(folder):
    app=TiddlyWikiApp(lambda:None)
    app.wiki=folder/'wiki';(app.wiki/'tiddlers').mkdir(parents=True)
    (app.wiki/'tiddlers/note.tid').write_text('title: Existing\n\nExact text',encoding='utf-8')
    app.page=Mock()
    assert app.title_exists('Existing')
    app.page.evaluate.assert_not_called()
    app.page.evaluate.return_value=False
    assert not app.title_exists('New')


def test_personal_diagnostics_never_capture_note_contents():
    # Constructor is deliberately lazy; no path access or personal data.
    storage=NotesStorage.personal()
    app=TiddlyWikiApp(lambda:None,storage=storage);app.page=Mock()
    app._diagnose()
    app.page.evaluate.assert_not_called()
