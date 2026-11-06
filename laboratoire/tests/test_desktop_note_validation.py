import queue
import threading
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from types import SimpleNamespace
import pytest
from desktop_note_validation import commit_review
from observer_note_pending import PendingNoteReview


def context():
    app=SimpleNamespace(stop=threading.Event(),inputs=queue.Queue())
    pending=PendingNoteReview()
    target={'title':'Validation','body':'Texte exact'}
    pending.propose(target,'local_text')
    authorization=pending.confirm(pending.review()['ticket'],'oui')
    return app,pending,authorization,target


def test_commit_once():
    app,pending,authorization,target=context()
    assert commit_review(app,pending,authorization)==target
    with pytest.raises(ValueError):commit_review(app,pending,authorization)


@pytest.mark.parametrize('interrupt',['stop','queued_input','cancel'])
def test_interrupted_review_never_commits(interrupt):
    app,pending,authorization,target=context()
    if interrupt=='stop':app.stop.set()
    elif interrupt=='queued_input':app.inputs.put('Correction')
    else:pending.cancel()
    with pytest.raises(ValueError):commit_review(app,pending,authorization)
