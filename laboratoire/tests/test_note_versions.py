from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tempfile
from unittest.mock import Mock
import pytest
from protected_workspace import ROOT
from notes_storage import NotesStorage
from note_versions import remember, version_store, document_name, handle

@pytest.fixture
def storage():
    with tempfile.TemporaryDirectory(prefix='validation_note_versions_',dir=ROOT/'data/validation') as folder:
        yield NotesStorage.validation(Path(folder)/'wiki')

def test_notes_have_durable_original_and_current_copies(storage):
    a=remember(storage,{'title':'validation_note','body':'original'})
    b=remember(storage,{'title':'validation_note','body':'nouveau'})
    store=version_store(storage);name=document_name('validation_note')
    assert {r['id'] for r in store.history(name,source='text')}=={a,b}
    assert store.read(name,source='text')['body']=='nouveau'

def test_note_restore_preview_and_real_permission_consumption(storage):
    original={'title':'validation_note','body':'original'}
    revision=remember(storage,original)
    backend=Mock(storage=storage)
    backend.read_note.return_value={'title':'validation_note','body':'actuel'}
    backend.verify_persisted.return_value=True
    seen=[]
    def execute(session,app,target,commit):
        permit=commit();seen.append((target,permit))
        return {'passed':True}
    confirm=Mock(return_value=True)
    result=handle('/restaurer-note validation_note | '+revision,'text',Mock(),
                  lambda guard:backend,execute,confirm,lambda:False)
    assert result['status']=='restored' and seen[0][0]==original
    assert 'Avant :\nactuel' in confirm.call_args.args[0]
    assert 'Apres :\noriginal' in confirm.call_args.args[0]
    backend.close.assert_called_once()

def test_note_restore_refusal_never_calls_executor(storage):
    revision=remember(storage,{'title':'validation_note','body':'original'})
    backend=Mock(storage=storage);backend.read_note.return_value={'title':'validation_note','body':'actuel'}
    execute=Mock()
    result=handle('/restaurer-note validation_note | '+revision,'text',Mock(),
                  lambda guard:backend,execute,lambda _:False,lambda:False)
    assert result['status']=='cancelled'
    execute.assert_not_called();backend.prepare_edit.assert_not_called()

def test_note_history_rejects_external_source_before_factory():
    factory=Mock()
    with pytest.raises(ValueError):handle('/versions-note validation_note','discord',Mock(),factory,Mock(),Mock(),lambda:False)
    factory.assert_not_called()
