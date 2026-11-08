"""Local link requests and short-lived clarification; no page content in memory."""
import time
from link_request import can_handle_link, is_link_followup, interpret_link
from public_link_navigation import read_linked


class LinkDialogue:
    def __init__(self,session,*,planner=interpret_link,reader=read_linked,clock=time.monotonic):
        self.session,self.planner,self.reader,self.clock=session,planner,reader,clock
        self.turns=[];self.last_turn=None

    def cancel(self):
        self.turns=[];self.last_turn=None

    def _expire(self):
        if self.last_turn is not None and not 0<=self.clock()-self.last_turn<300:self.cancel()

    def can_handle(self,text):
        self._expire()
        return can_handle_link(text) or bool(self.turns and is_link_followup(text))

    def handle(self,text,source,*,cancelled=lambda:False):
        if source not in ('text','voice'):raise ValueError('local_link_request_required')
        def check():
            self.session.check()
            if cancelled():raise ValueError('link_interrupted')
        try:
            check();self._expire()
            if can_handle_link(text):self.cancel()
            if not self.turns and not can_handle_link(text):
                return {'status':'clarify','reply':'Donne la page HTTPS, le nom du lien a suivre et ta question sur la page d arrivee.'}
            if type(text) is not str or len(self.turns)>=8 or sum(map(len,self.turns))+len(text)>16000:
                self.cancel()
                return {'status':'clarify','reply':'Recommence avec la page, le nom du lien et ta question.'}
            self.turns.append(text);self.last_turn=self.clock()
            intent=self.planner(self.session,list(self.turns),source)
            check()
            if intent['status'] in ('cancel','discuss'):
                self.cancel()
                return {'status':'cancelled','reply':'Je ne lance pas de navigation pour cette phrase.'}
            if intent['status']!='ready':
                return {'status':'clarify','reply':'Precise la page HTTPS, le nom exact du lien et la question a verifier. Tu peux completer avec « le lien est... » ou « la question est... ».'}
            target=intent['target']
            result=self.reader(self.session,target['url'],target['label'],target['question'],source=source,cancelled=cancelled)
            check()
            if result['status']!='clarify':self.cancel()
            return result
        except (ValueError,RuntimeError,OSError) as error:
            self.cancel()
            self.session.check()
            if cancelled():return {'status':'cancelled','reply':'Navigation interrompue.'}
            return {'status':'failed','error_type':type(error).__name__,
                'reply':'Je n ai pas pu verifier cette navigation. Aucune information confirmee sur la page d arrivee.'}


def run_link_turn(app,text,source):
    epoch=app.speech_epoch
    cancelled=lambda:app.stop.is_set() or not app.inputs.empty() or app.session.voice.interruption_epoch!=epoch
    result=app.links.handle(text,source,cancelled=cancelled)
    app.observation.emit('web.link_result',{'status':result['status'],'error_type':result.get('error_type','')})
    if cancelled():return result
    if result.get('url'):app.events.put(('text',('Source consultee',result['url'])))
    if result.get('from_url'):app.events.put(('text',('Page de depart',result['from_url'])))
    app.say(result['reply'])
    if result.get('partial'):
        app.events.put(('text',('Lecture limitee','Cette lecture publique peut etre partielle. Images et comptes non pris en charge.')))
    return result
