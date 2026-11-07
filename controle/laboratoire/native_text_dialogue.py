"""Local literal-text request -> unique target -> one-use permission -> service.

Inventory and backend factory are provided by the desktop integration. The
factory owns focus consent and cleanup; it must not activate a window silently
while the user is busy. This controller never launches programs or saves files.
"""
from .native_text_request import interpret
from .native_target_selection import select_window, select_text_control
from .native_task_permission import NativeTaskPermission
from .native_text_service import run_authorized_text


def failure_reply(error):
    replies = {
        'native_game_active': 'Un jeu est ouvert. Je ne prends pas le clavier ni la souris pendant ta partie ; cette prise de controle reste a valider.',
        'native_ram_low': 'Il reste trop peu de memoire disponible pour cette action. Je me suis arretee.',
        'native_focus_required': 'Windows ne me laisse pas activer cette fenetre. Mets le document vise au premier plan puis redemande-moi la saisie.',
        'native_window_missing_or_ambiguous': 'Je ne trouve pas une fenetre unique correspondant a ta demande. Precise son titre exact, ou ouvre un seul Bloc-notes pour cette tache.',
        'native_existing_text_needs_explicit_revision': 'Ce document contient deja un autre texte. Je ne sais pas encore le remplacer ou le completer de facon verifiee.',
        'native_request_interrupted': 'Saisie interrompue.',
    }
    return replies.get(str(error), 'Je ne peux pas confirmer cette saisie : la fenetre ou le champ ne sont pas suffisamment verifies. Je me suis arretee.')


class NativeTextDialogue:
    def __init__(self, session, inventory, backend_factory, *, allowed_processes,
                 executor=run_authorized_text):
        self.session,self.inventory,self.factory=session,inventory,backend_factory
        self.allowed=tuple(allowed_processes)
        self.executor=executor
        self.permissions=NativeTaskPermission()

    def cancel(self): self.permissions.cancel()

    def can_handle(self,text,source):
        return interpret(text,source)['status']!='not_handled'

    def handle(self,text,source,*,cancelled=lambda:False):
        # Parse before any inventory/read. External source raises before PC access.
        intent=interpret(text,source)
        self.cancel()
        if intent['status']!='ready':
            return {'status':intent['status'],'verified':False,
                    'reply':intent.get('reply','Precise la fenetre et le texte exact a saisir.')}
        def check():
            self.session.check()
            if cancelled(): raise RuntimeError('native_request_interrupted')
        try:
            check()
            selected=select_window(self.inventory(),intent['target']['window_hint'],allowed_processes=self.allowed)
            check()
            # No model text or display content can select another process.
            with self.factory(selected['window'],cancelled=cancelled) as backend:
                check()
                scene=backend.observer.read()
                if scene['window']!=selected['window']:
                    raise ValueError('native_selected_window_changed')
                current=select_window(self.inventory(),intent['target']['window_hint'],allowed_processes=self.allowed)
                if current!=selected:
                    raise ValueError('native_selected_document_changed')
                target=select_text_control(scene,intent['target']['text'])
                context_factory=getattr(backend,'typing_context_factory',None)
                typing_context=context_factory(scene,target) if context_factory else None
                task={'window':selected['window'],'target':target,'text':intent['target']['text']}
                review=self.permissions.propose(task,source=source)
                # The exact local imperative itself authorizes this limited text
                # operation. Permission to steal focus is NOT implied here.
                permit=self.permissions.approve(review['ticket'],True,source=source)
                check()
                return self.executor(self.session,backend.observer,backend.transport,
                                     self.permissions,permit,task,cancelled=cancelled,
                                     typing_context=typing_context)
        except Exception as error:
            self.cancel()
            return {'status':'unverified','verified':False,'reason':type(error).__name__,
                    'reply':failure_reply(error)}
        finally:
            self.cancel()
