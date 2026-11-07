from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_task_runner as runner


def run(responses, **kwargs):
    adapter = Mock()
    with patch.object(runner, 'step', side_effect=responses) as step:
        result = runner.run_task(Mock(),adapter,{'hwnd':1},'goal',{},Mock(),Mock(),**kwargs)
    return result, adapter, step


def test_verified_progress_then_complete():
    result, adapter, step = run([
        {'status':'verified','verified':True,'action':{'op':'click','target':'field'}},
        {'status':'complete','verified':True}])
    assert result['status']=='complete' and len(result['steps'])==2
    adapter.cancel.assert_called_once()
    assert step.call_args.args[-1] == [{'action':{'op':'click','target':'field'},'result':'verified'}]


@pytest.mark.parametrize('status',['uncertain','refused','unverified','clarify'])
def test_no_retry_after_non_verified_action(status):
    result, adapter, step = run([{'status':status,'verified':False}])
    assert result['status']==status and not result['verified']
    step.assert_called_once(); adapter.cancel.assert_called_once()


def test_reobserve_is_bounded_without_action_history():
    result, adapter, step = run([{'status':'reobserve','verified':False}]*3)
    assert result['status']=='reobserve' and step.call_count==3
    assert all(call.args[-1]==[] for call in step.call_args_list)


def test_step_limit_stops_task():
    result, adapter, step = run([{'status':'verified','verified':True,'action':{'op':'click'}}]*2,max_steps=2)
    assert result['status']=='step_limit'
    adapter.cancel.assert_called_once()


def test_cancelled_before_planning():
    result, adapter, step = run([],cancelled=lambda:True)
    assert result['status']=='interrupted'
    step.assert_not_called(); adapter.cancel.assert_called_once()


def test_failure_stops_adapter_without_replay():
    result, adapter, step = run([TimeoutError()])
    assert result['status']=='interrupted'
    step.assert_called_once(); adapter.cancel.assert_called_once()


def test_premature_done_gets_one_feedback_replan_only():
    premature={'status':'clarify','verified':False,'reason':'goal_not_verified','proposed_op':'done'}
    result,adapter,step=run([premature,premature])
    assert result['status']=='clarify' and step.call_count==2
    assert step.call_args.args[-1][0]['result']=='goal_not_verified'
    adapter.cancel.assert_called_once()


def test_deadline_checked_after_step():
    clock=Mock(side_effect=[0,0,61])
    result, adapter, step=run([{'status':'complete','verified':True}],clock=clock)
    assert result['status']=='interrupted'
    adapter.cancel.assert_called_once()


def test_real_controller_and_runner_on_synthetic_application():
    base={'state':{'window':{'hwnd':1,'pid':2,'created':3},'available':True,'foreground':True,
        'elements':[{'id':'edit1','name':'Texte de la note','type':'ControlType.Edit','value':'',
        'focused':True,'visible':True,'enabled':True,'actions':['click','type']}]}}
    def scripted_decision(session, goal, snapshot, texts, history):
        elements=snapshot['state']['elements']
        if elements[0]['value']!=texts['body']:
            if not elements[0]['focused']:return {'op':'click','target':'edit1'}
            return {'op':'type','target':'edit1','text':texts['body']}
        return {'op':'click','target':'save1'}
    with patch('native_action_planner.choose',side_effect=scripted_decision):
        rows=sequential_cases(Mock(),base)
    assert all(row['passed'] and row['adapter_stopped'] for row in rows)
    assert [[a['op'] for a in row['actions']] for row in rows]==[['click','type'],['click','type','click']]


class SyntheticDesktop:
    """In-memory application state, deliberately no Windows transport."""
    def __init__(self, state): self.state=deepcopy(state); self.stopped=False; self.actions=[]
    def read(self): return deepcopy(self.state)
    def cancel(self): self.stopped=True
    def dispatch(self, action, *, expected, cancelled):
        if self.stopped or cancelled() or expected != self.state:
            raise RuntimeError('synthetic_scene_changed')
        self.actions.append(deepcopy(action))
        elements=self.state['elements']
        if action['op']=='type':
            next(e for e in elements if e['id']==action['target'])['value'] += action['text']
        elif action['op']=='click':
            for element in elements: element['focused']=element['id']==action['target']
            if action['target']=='save1':
                elements[-1]['value']=elements[0]['value']
        else: raise ValueError('synthetic_action_unsupported')

def sequential_cases(session,base):
    rows=[]
    for name,text,save_required in [('focus_and_type','validation_liste_fictive',False),
                                    ('type_and_save','validation_rendez_vous',True)]:
        state=deepcopy(base['state']); state['elements'][0]['focused']=False
        state['elements'].extend([
            {'id':'save1','name':'Enregistrer','type':'ControlType.Button','visible':True,
             'enabled':True,'focused':False,'actions':['click'] if save_required else [],'value':None},
            {'id':'saved1','name':'Texte enregistre','type':'ControlType.Text','visible':True,
             'enabled':True,'focused':False,'actions':[],'value':''}])
        adapter=SyntheticDesktop(state)
        def satisfied(current):
            return current['elements'][-1 if save_required else 0]['value']==text
        def verify(action,before,after):
            if action['op']=='type': return after['elements'][0]['value']==text
            if action['target']=='edit1': return after['elements'][0]['focused'] is True
            return action['target']=='save1' and after['elements'][-1]['value']==text
        goal='Dans le champ Texte de la note, saisis exactement body du registre.'
        goal+=' Puis clique Enregistrer.' if save_required else ' Ne clique pas Enregistrer.'
        outcome=runner.run_task(session,adapter,state['window'],goal,{'body':text},satisfied,verify)
        rows.append({'case':name,'passed':outcome['status']=='complete','result':outcome,
                     'actions':adapter.actions,'adapter_stopped':adapter.stopped})
        print(name,rows[-1]['passed'],flush=True)
    return rows
