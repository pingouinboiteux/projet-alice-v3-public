"""Bounded model/observe/act loop for an explicitly authorized native task.

The caller supplies the bound adapter, grants, exact text and independent
postconditions. This module cannot discover windows or grant itself permissions.
"""
import threading
import time

from .native_action_control import NativeActionControl
from .native_action_planner import step


def run_task(session, adapter, window, goal, texts, satisfied, verify, *,
             cancelled=lambda: False, seconds=60, max_steps=8, clock=time.monotonic):
    if type(seconds) not in (int, float) or not 0 < seconds <= 120:
        raise ValueError('native_task_budget_invalid')
    if type(max_steps) is not int or not 1 <= max_steps <= 12:
        raise ValueError('native_task_steps_invalid')
    deadline = clock() + seconds
    def guard():
        session.check()
        if cancelled(): raise RuntimeError('native_task_cancelled')
        if clock() >= deadline: raise RuntimeError('native_task_deadline')
    controller = NativeActionControl(adapter, window, guard, clock=clock, max_age=10)
    timer = threading.Timer(seconds, controller.stop)
    timer.daemon = True
    timer.start()
    rows, history = [], []
    scene_changes = 0
    premature_done = 0
    try:
        for _ in range(max_steps):
            guard()
            result = step(session, controller, goal, texts, satisfied, verify, history)
            rows.append(result)
            guard()
            status = result['status']
            if status == 'complete' and result.get('verified') is True:
                return {'status':'complete', 'verified':True, 'steps':rows}
            if (status=='clarify' and result.get('proposed_op')=='done'
                    and result.get('reason')=='goal_not_verified' and premature_done==0):
                premature_done+=1
                history.append({'result':'goal_not_verified',
                    'feedback':'Le controle independant ne confirme pas la fin. Relis la demande et l etat observe ; verifie les etapes restantes avant de conclure.'})
                continue  # No input was sent by done; one evidence-led replan.
            if status == 'reobserve':
                scene_changes += 1
                if scene_changes <= 2:
                    continue  # No action was sent; fresh planning is permitted.
            if status != 'verified':
                return {'status':status, 'verified':False, 'steps':rows}
            history.append({'action':result['action'], 'result':'verified'})
        return {'status':'step_limit', 'verified':False, 'steps':rows}
    except Exception as error:
        result = {'status':'interrupted', 'verified':False, 'steps':rows,
                  'reason':type(error).__name__}
        code = str(error)
        if (code.startswith('native_') and len(code) <= 100
                and all(c in 'abcdefghijklmnopqrstuvwxyz_' for c in code)):
            result['code'] = code
        return result
    finally:
        timer.cancel()
        controller.stop()
