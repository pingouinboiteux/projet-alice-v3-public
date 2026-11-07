"""Execute only the exact text/window/control covered by a local permission."""
from copy import deepcopy
from .native_windows_adapter import NativeWindowsAdapter
from .native_task_runner import run_task


def run_authorized_text(session, observer, transport, permissions, permit, task, *, cancelled=lambda:False,
                        typing_context=None):
    task=deepcopy(task)
    lease=permissions.claim(permit,task)
    def interrupted(): return cancelled() or not permissions.active(lease)
    def guard():
        session.check()
        if interrupted(): raise RuntimeError('native_text_permission_ended')
    target,text=task['target'],task['text']
    adapter=NativeWindowsAdapter(observer,transport,{target:{'actions':['click','type']}},guard,
                                 typing_context=typing_context)
    def check_document(state):
        if typing_context is not None:
            if typing_context.target != target:
                raise RuntimeError('native_typing_context_target_mismatch')
            typing_context.project(state)
    def value(state):
        if state.get('window')!=task['window']: return None
        check_document(state)
        values=[e.get('value') for e in state['elements'] if e['id']==target]
        return values[0] if len(values)==1 else None
    def satisfied(state): return value(state)==text
    def verify(action,before,after):
        if action.get('target')!=target or after.get('window')!=task['window']: return False
        check_document(after)
        if action['op']=='type': return value(after)==text
        if action['op']=='click':
            return any(e['id']==target and e.get('focused') is True for e in after['elements'])
        return False
    try:
        guard()
        result=run_task(session,adapter,task['window'],
            'Saisis exactement body du registre dans le controle '+target+'. Ne fais aucune autre action.',
            {'body':text},satisfied,verify,cancelled=interrupted)
        result['reply']=('Le texte demande est bien present dans la fenetre et a ete relu.'
            if result.get('verified') else 'La saisie n est pas confirmee. Je me suis arretee ; verifie la fenetre avant de recommencer.')
        return result
    finally:
        adapter.cancel()
        permissions.finish(lease)
