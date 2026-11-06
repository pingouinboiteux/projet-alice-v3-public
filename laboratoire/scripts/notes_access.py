"""Local list/read/update of notes; stored text never becomes model instructions."""
import time
from note_operations import operation_kind, interpret_operation
from observer_note_intent import _FIELD, _CORRECTION, _CANCEL

class NotesAccess:
    def __init__(self, session, *, factory, executor, pending,
                 planner=interpret_operation, clock=time.monotonic):
        self.session,self.factory,self.executor=session,factory,executor
        self.pending,self.planner,self.clock=pending,planner,clock
        self.turns=[];self.operation=None;self.last_turn=None

    def cancel(self):
        self.pending.cancel()
        self.turns=[];self.operation=None;self.last_turn=None

    def can_handle(self,text):
        if self.last_turn is not None and not 0 <= self.clock()-self.last_turn < 300:
            self.cancel()
        return bool(operation_kind(text) or (self.turns and
            (_CORRECTION.search(text) or _CANCEL.search(text) or any(p.search(text) for p in _FIELD.values()))))

    def handle(self,text,source,confirm,cancelled=lambda:False, *, automatic=False):
        if source not in ('text','voice'):raise ValueError('Local notes only')
        backend=None
        def check():
            self.session.check()
            if cancelled():raise ValueError('note_request_interrupted')
        try:
            check()
            operation=operation_kind(text)
            if operation:
                self.cancel();self.operation=operation
            if self.operation is None:
                return {'status':'clarify','reply':'Precise si tu veux lister, lire ou modifier une note.'}
            if len(self.turns)>=8 or sum(map(len,self.turns))+len(text)>16000:
                self.cancel()
                return {'status':'clarify','reply':'Reformule la demande avec le titre exact et, pour modifier, le nouveau texte complet.'}
            self.turns.append(text);self.last_turn=self.clock()
            intent=self.planner(self.session,list(self.turns),self.operation,source)
            check()
            if intent['status']=='cancel':
                self.cancel()
                return {'status':'cancelled','reply':'Demande annulee. Aucune modification enregistree.'}
            if intent['status']!='ready':
                return {'status':'clarify','reply':'Precise le titre exact de la note et, pour modifier, le nouveau texte complet.'}
            if automatic and self.operation=='update':
                from note_request import decide_note
                decision=decide_note(self.session,list(self.turns),'update',intent,source)
                check()
                if decision!='execute':
                    self.pending.cancel()
                    return {'status':'clarify','reply':'Rien modifie. Precise si tu veux remplacer maintenant tout le texte de la note ou liste, avec son titre et le nouveau texte complet.'}
            backend=self.factory(check);backend.start()
            if self.operation=='list':
                listing=backend.list_notes(limit=20);check();self.cancel()
                titles=listing['titles']
                reply=('Tes notes :\n'+'\n'.join(titles)) if titles else 'Aucune note enregistree.'
                if listing['truncated']:reply+='\nListe limitee aux 20 premiers titres.'
                return {'status':'listed','reply':reply}
            existing=backend.read_note(intent['title']);check()
            if existing is None:
                return {'status':'missing','reply':'Je ne trouve pas de note avec ce titre exact. Tu peux demander la liste des notes.'}
            if self.operation=='read':
                self.cancel()
                return {'status':'read','reply':existing['title']+' :\n'+existing['body']}
            if self.operation!='update':raise ValueError('unsupported_note_operation')
            target={'title':existing['title'],'body':intent['body']}
            if target==existing:
                self.cancel()
                return {'status':'unchanged','reply':'La note contient deja exactement ce texte. Rien a modifier.'}
            self.pending.propose(target,'voice' if source=='voice' else 'local_text')
            review=self.pending.review()
            description=('Modifier seulement le texte de la note '+existing['title']+'.\n'
                +('Transcription vocale : verifie chaque mot.\n' if source=='voice' else '')
                +'\nTexte actuel :\n'+existing['body']+'\n\nNouveau texte :\n'+target['body']
                +'\n\nLe titre reste identique. Annule pour corriger.')
            if not automatic and not confirm(description):
                self.pending.cancel()
                return {'status':'cancelled','reply':'Aucune modification enregistree. Tu peux corriger ta demande.'}
            check()
            authorization=(self.pending.authorize_request(review['ticket'],source='voice' if source=='voice' else 'local_text')
                           if automatic else self.pending.confirm(review['ticket'],'oui'))
            backend.prepare_edit(existing)
            def commit():
                check();return self.pending.claim(authorization)
            outcome=self.executor(self.session,backend,target,commit)
            check()
            verified=bool(outcome.get('passed') and backend.verify_persisted(target))
            self.cancel()
            if verified:return {'status':'updated','reply':'Note modifiee et relue : '+target['title']+'.'}
            return {'status':'unverified','reply':'Je ne peux pas confirmer la modification de la note.'}
        except Exception as error:
            self.cancel()
            if str(error)=='note_changed':
                return {'status':'conflict','reply':'La note a change depuis sa lecture. Recommence pour verifier sa nouvelle version.'}
            return {'status':'failed','error_type':type(error).__name__,
                    'reply':'La demande de note a ete interrompue ou a echoue. Aucun resultat confirme.'}
        finally:
            if backend is not None:backend.close()
