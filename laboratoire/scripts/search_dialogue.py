"""Local search requests and bounded clarification; no page content in memory."""
import time
from search_request import can_handle_search, is_search_followup, interpret_search
from brave_web_search import read_brave_search as read_search


def _recoverable_search_error(error):
    if isinstance(error,(ValueError,RuntimeError,OSError)):
        return True
    # Keep Playwright optional until browser use; its errors do not inherit
    # Python's RuntimeError or TimeoutError. Never swallow programming errors.
    try:
        from playwright.sync_api import Error as BrowserError
    except ImportError:
        return False
    return isinstance(error,BrowserError)


class SearchDialogue:
    def __init__(self,session,*,planner=interpret_search,reader=read_search,clock=time.monotonic):
        self.session,self.planner,self.reader,self.clock=session,planner,reader,clock
        self.turns=[];self.last_turn=None;self.routed=False

    def cancel(self):
        self.turns=[];self.last_turn=None;self.routed=False

    def _expire(self):
        if self.last_turn is not None and not 0<=self.clock()-self.last_turn<300:self.cancel()

    def can_handle(self,text):
        self._expire()
        return can_handle_search(text) or bool(self.turns and is_search_followup(text))

    def handle(self,text,source,*,cancelled=lambda:False,routed=False):
        if source not in ('text','voice'):raise ValueError('local_search_request_required')
        if type(routed) is not bool:raise ValueError('invalid_routed_provenance')
        def check():
            self.session.check()
            if cancelled():raise ValueError('search_interrupted')
        try:
            check();self._expire()
            if routed or can_handle_search(text):
                self.cancel()
                self.routed=routed
            if not self.turns and not can_handle_search(text) and not routed:
                return {'status':'clarify','reply':'Donne une question precise a chercher sur internet.'}
            if self.turns and not is_search_followup(text):
                self.cancel()
                return {'status':'clarify','reply':'Donne une question precise a chercher sur internet.'}
            if type(text) is not str or len(self.turns)>=8 or sum(map(len,self.turns))+len(text)>16000:
                self.cancel()
                return {'status':'clarify','reply':'Recommence avec une question precise (500 caracteres maximum).'}
            self.turns.append(text);self.last_turn=self.clock()
            intent=self.planner(self.session,list(self.turns),source,**({'routed':True} if self.routed else {}))
            check()
            if intent['status'] in ('cancel','discuss'):
                self.cancel()
                return {'status':'cancelled','reply':'Je ne lance pas de recherche pour cette phrase.'}
            if intent['status']!='ready':
                return {'status':'clarify','reply':'Precise le sujet, le lieu ou les contraintes utiles. Tu peux remplacer ta demande avec « la recherche est... » ou « la question est... ».'}
            target=intent['target']
            result=self.reader(self.session,target['question'],source=source,cancelled=cancelled)
            check()
            if result.get('status') in ('found','ambiguous') and result.get('evidence'):
                # A reference and matching numbers cannot prove a paraphrase.
                # Keep the browser's exact excerpts as the spoken answer.
                result={**result,'answer_style':'verified_quotes'}
            if result['status'] not in ('clarify','ambiguous','missing'):self.cancel()
            return result
        except Exception as error:
            if not _recoverable_search_error(error):raise
            self.cancel()
            self.session.check()
            if cancelled():return {'status':'cancelled','reply':'Recherche interrompue.'}
            return {'status':'failed','error_type':type(error).__name__,
                'reply':'Je n ai pas pu verifier cette recherche. Aucune information Web confirmee.'}


def run_search_turn(app,text,source,*,routed=False):
    epoch=app.speech_epoch
    cancelled=lambda:app.stop.is_set() or not app.inputs.empty() or app.session.voice.interruption_epoch!=epoch
    result=app.searches.handle(text,source,cancelled=cancelled,routed=routed)
    app.observation.emit('web.search_result',{'status':result['status'],'error_type':result.get('error_type','')})
    if cancelled():return result
    if result.get('sources'):app.events.put(('text',('Sources consultees','\n'.join(result['sources']))))
    if result.get('verified_excerpts'):
        app.events.put(('text',('Extraits verifies',result['verified_excerpts'])))
    app.say(result['reply'])
    if result.get('partial'):
        app.events.put(('text',('Lecture limitee','Cette lecture publique peut etre partielle. Images et comptes non pris en charge.')))
    return result
