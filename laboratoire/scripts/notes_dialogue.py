"""Local note requests, exact-source extraction and explicit one-use review.

Construction opens no store or browser. Notes never use the personal memory or
public scene. Direct note requests bypass the general action router.
"""
import json
import time
from observer_note_intent import (_CREATE, _FIELD, _CORRECTION, _CANCEL,
    SCHEMA, validate_intent, apply_input_policy)
from observer_note_revision import payload_for_revision
from observer_note_pending import PendingNoteReview

def interpret(session, turns, source):
    raw,_,_=session.ask(payload_for_revision(turns)['messages'],response_schema=SCHEMA)
    return apply_input_policy(validate_intent(json.loads(raw),turns),source)

def backend_factory(guard):
    from notes_storage import NotesStorage
    from observer_tiddlywiki import TiddlyWikiApp
    return TiddlyWikiApp(guard,storage=NotesStorage.personal())

def execute(session, backend, target, before_commit):
    from observer_value_bench import complete
    return complete(session,backend,target,before_commit=before_commit)

class NotesDialogue:
    def __init__(self, session, *, factory=backend_factory, planner=interpret,
                 executor=execute, clock=time.monotonic):
        self.session,self.factory,self.planner,self.executor=session,factory,planner,executor
        self.clock=clock
        self.pending=PendingNoteReview(clock=clock)
        self.turns=[]
        self.last_turn=None
        self.access=None

    def cancel(self):
        self.pending.cancel()
        self.turns=[]
        self.last_turn=None
        if self.access is not None:self.access.cancel()

    def can_handle(self,text):
        if type(text) is not str:return False
        if text.startswith(('/versions-note ', '/restaurer-note ')):return True
        from note_operations import operation_kind
        if operation_kind(text) or (self.access is not None and self.access.can_handle(text)):
            return True
        if self.last_turn is not None and not 0 <= self.clock()-self.last_turn < 300:
            self.cancel()
        if _CREATE.search(text):return True
        return bool(self.turns and (_CANCEL.search(text) or _CORRECTION.search(text)
                    or any(p.search(text) for p in _FIELD.values())))

    def handle(self,text,source,confirm,cancelled=lambda:False, *, automatic=False):
        if source not in ('text','voice'):
            raise ValueError('Local note requests only')
        from note_versions import handle as handle_versions
        version_result=handle_versions(text,source,self.session,self.factory,self.executor,confirm,cancelled)
        if version_result is not None:
            self.cancel()
            return version_result
        from note_operations import operation_kind
        if operation_kind(text) or (not _CREATE.search(text) and self.access is not None and self.access.can_handle(text)):
            if self.access is None:
                from notes_access import NotesAccess
                self.access=NotesAccess(self.session,factory=self.factory,executor=self.executor,
                    pending=self.pending,clock=self.clock)
            self.turns=[];self.last_turn=None
            return self.access.handle(text,source,confirm,cancelled,automatic=automatic)
        origin='local_text' if source=='text' else 'voice'
        def check():
            self.session.check()
            if cancelled():raise ValueError('note_request_interrupted')
        backend=None
        try:
            check()
            if _CREATE.search(text):self.cancel()
            if not self.turns and not _CREATE.search(text):
                return {'status':'clarify','reply':'Precise si tu veux creer, lire, lister ou modifier une note, avec son titre exact et le texte complet si necessaire.'}
            if len(self.turns)>=8 or sum(map(len,self.turns))+len(text)>16000:
                self.cancel()
                return {'status':'clarify','reply':'Reformule la note avec son titre et son texte dans une nouvelle demande.'}
            self.turns.append(text);self.last_turn=self.clock()
            intent=self.planner(self.session,list(self.turns),origin)
            check()
            if intent['status']=='cancel':
                self.cancel()
                return {'status':'cancelled','reply':'Demande annulee. Aucune note enregistree.'}
            if intent['status'] not in ('ready','needs_confirmation'):
                return {'status':'clarify','reply':'Precise le titre et le texte exacts de la note, ou la correction souhaitee.'}
            target=intent['target']
            if automatic:
                from note_request import decide_note
                decision=decide_note(self.session,list(self.turns),'create',intent,source)
                check()
                if decision!='execute':
                    self.pending.cancel()
                    return {'status':'clarify','reply':'Rien enregistre. Precise si tu veux creer maintenant cette note ou liste, avec son titre et son texte exacts.'}
            self.pending.propose(target,origin)
            review=self.pending.review()
            description=('Creer une note conservee apres fermeture d Alice.\n'
                +('Transcription vocale : verifie chaque mot.\n' if source=='voice' else '')
                +'\nTitre : '+target['title']+'\n\nTexte :\n'+target['body']
                +'\n\nUne note du meme titre ne sera pas remplacee. Annule pour corriger.')
            if not automatic and not confirm(description):
                self.pending.cancel()
                return {'status':'cancelled','reply':'Rien enregistre. Tu peux corriger la demande ou l abandonner.'}
            check()
            authorization=(self.pending.authorize_request(review['ticket'],source=origin) if automatic
                           else self.pending.confirm(review['ticket'],'oui',source='local_text'))
            backend=self.factory(check)
            backend.start()
            if backend.title_exists(target['title']):
                self.pending.cancel()
                return {'status':'exists','reply':'Une note porte deja ce titre. Elle reste intacte ; choisis un autre titre.'}
            backend.prepare_new()
            def commit():
                check()
                return self.pending.claim(authorization)
            outcome=self.executor(self.session,backend,target,commit)
            check()
            verified=bool(outcome.get('passed') and backend.verify_persisted(target))
            self.cancel()
            if verified:return {'status':'saved','reply':'Note enregistree et relue : '+target['title']+'.'}
            return {'status':'unverified','reply':'Je ne peux pas confirmer l enregistrement de la note. Aucun succes verifie.'}
        except Exception as error:
            self.cancel()
            return {'status':'failed','error_type':type(error).__name__,
                    'reply':'La creation de note a ete interrompue ou a echoue. Je ne peux pas confirmer son enregistrement.'}
        finally:
            if backend is not None:backend.close()

def run_local_turn(app,controller,text,source):
    epoch=app.speech_epoch
    result=controller.handle(text,source,app.confirm,
        cancelled=lambda:app.stop.is_set() or not app.inputs.empty()
            or app.session.voice.interruption_epoch!=epoch,automatic=True)
    app.observation.emit('notes.result',{'status':result['status'],
        'error_type':result.get('error_type','')})
    app.say(result['reply'])
    return result
