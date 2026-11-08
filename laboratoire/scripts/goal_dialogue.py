"""Local goal requests and bounded clarification; no page content in memory."""
import time
from goal_request import can_handle_goal, is_goal_followup, interpret_goal
from public_goal_navigation import read_goal


class GoalDialogue:
    def __init__(self,session,*,planner=interpret_goal,reader=read_goal,clock=time.monotonic):
        self.session,self.planner,self.reader,self.clock=session,planner,reader,clock
        self.turns=[];self.last_turn=None

    def cancel(self):
        self.turns=[];self.last_turn=None

    def _expire(self):
        if self.last_turn is not None and not 0<=self.clock()-self.last_turn<300:self.cancel()

    def can_handle(self,text):
        self._expire()
        return can_handle_goal(text) or bool(self.turns and is_goal_followup(text))

    def handle(self,text,source,*,cancelled=lambda:False):
        if source not in ('text','voice'):raise ValueError('local_goal_request_required')
        def check():
            self.session.check()
            if cancelled():raise ValueError('goal_interrupted')
        try:
            check();self._expire()
            if can_handle_goal(text):self.cancel()
            if not self.turns and not can_handle_goal(text):
                return {'status':'clarify','reply':'Donne la page HTTPS de depart et l information a chercher.'}
            if type(text) is not str or len(self.turns)>=8 or sum(map(len,self.turns))+len(text)>16000:
                self.cancel()
                return {'status':'clarify','reply':'Recommence avec la page HTTPS et ta question.'}
            self.turns.append(text);self.last_turn=self.clock()
            intent=self.planner(self.session,list(self.turns),source)
            check()
            if intent['status'] in ('cancel','discuss'):
                self.cancel()
                return {'status':'cancelled','reply':'Je ne lance pas de navigation pour cette phrase.'}
            if intent['status']!='ready':
                return {'status':'clarify','reply':'Precise la page HTTPS de depart et la question a verifier. Tu peux completer avec « la page est... » ou « la question est... ».'}
            target=intent['target']
            result=self.reader(self.session,target['url'],target['question'],source=source,cancelled=cancelled)
            check()
            if result['status'] not in ('clarify','ambiguous','missing'):self.cancel()
            return result
        except (ValueError,RuntimeError,OSError) as error:
            self.cancel()
            self.session.check()
            if cancelled():return {'status':'cancelled','reply':'Navigation interrompue.'}
            return {'status':'failed','error_type':type(error).__name__,
                'reply':'Je n ai pas pu verifier cette navigation. Aucune information confirmee sur la page d arrivee.'}


def run_goal_turn(app,text,source):
    epoch=app.speech_epoch
    cancelled=lambda:app.stop.is_set() or not app.inputs.empty() or app.session.voice.interruption_epoch!=epoch
    result=app.goals.handle(text,source,cancelled=cancelled)
    app.observation.emit('web.goal_result',{'status':result['status'],'error_type':result.get('error_type','')})
    if cancelled():return result
    if result.get('url'):app.events.put(('text',('Source consultee',result['url'])))
    if result.get('visited'):app.events.put(('text',('Parcours consulte','\n'.join(result['visited']))))
    app.say(result['reply'])
    if result.get('partial'):
        app.events.put(('text',('Lecture limitee','Cette lecture publique peut etre partielle. Images et comptes non pris en charge.')))
    return result
