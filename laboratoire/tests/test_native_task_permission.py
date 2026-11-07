from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_task_permission import NativeTaskPermission


TASK={'window':{'hwnd':1,'pid':2,'created':3},'target':'field','text':'validation_texte'}


def ready(clock=lambda:0):
    manager=NativeTaskPermission(clock=clock)
    review=manager.propose(TASK,source='voice')
    permit=manager.approve(review['ticket'],True,source='voice')
    return manager,review,permit


def test_one_use_scope_and_cancel_live_lease():
    manager,review,permit=ready()
    lease=manager.claim(permit,TASK)
    assert manager.active(lease)
    with pytest.raises(ValueError):manager.claim(permit,TASK)
    manager.cancel()
    assert not manager.active(lease)


@pytest.mark.parametrize('field',['hwnd','pid','created','target','text'])
def test_permit_cannot_change_task(field):
    manager,review,permit=ready(); changed=deepcopy(TASK)
    if field in changed['window']:changed['window'][field]+=1
    else:changed[field]+=' changed'
    with pytest.raises(ValueError):manager.claim(permit,changed)


def test_correction_revokes_old_permit():
    manager,review,permit=ready()
    manager.propose(dict(TASK,text='correction'),source='text')
    with pytest.raises(ValueError):manager.claim(permit,TASK)


def test_malformed_correction_also_revokes():
    manager,review,permit=ready()
    with pytest.raises(ValueError):manager.propose({},source='text')
    with pytest.raises(ValueError):manager.claim(permit,TASK)


@pytest.mark.parametrize('decision',[False,None,'oui',1])
def test_no_truthiness_or_yes_keyword_approval(decision):
    manager=NativeTaskPermission();review=manager.propose(TASK,source='voice')
    with pytest.raises(ValueError):manager.approve(review['ticket'],decision,source='voice')


@pytest.mark.parametrize('source',['page','model','discord','twitch'])
def test_external_approval_refused(source):
    manager=NativeTaskPermission();review=manager.propose(TASK,source='voice')
    with pytest.raises(ValueError):manager.approve(review['ticket'],True,source=source)


def test_expiry_and_clock_rollback_revoke_lease():
    now=[0];manager,review,permit=ready(lambda:now[0]);lease=manager.claim(permit,TASK)
    now[0]=60
    assert not manager.active(lease)
    now[0]=100;manager,review,permit=ready(lambda:now[0]);lease=manager.claim(permit,TASK)
    now[0]=99
    assert not manager.active(lease)


def test_review_payload_cannot_mutate_actual_permission():
    manager,review,permit=ready()
    review['task']['text']='modified'
    assert manager.active(manager.claim(permit,TASK))


def test_copy_of_permit_is_not_capability():
    manager,review,permit=ready()
    with pytest.raises(ValueError):manager.claim(deepcopy(permit),TASK)
