"""Opt-in passive screen observation. No persistent images, tools or public output."""
from __future__ import annotations
import re
import threading
import time
import unicodedata
from screen_capture import monitors, capture, game_on_monitor
from screen_model import analyze
from screen_events import DeathEvents
from screen_ocr import detect

HELP = ('Vision : /ecran liste ; /ecran regarde 1 | ta question ; '
        '/ecran surveille 1 ; /ecran stop ; /ecran etat. '
        '1 = ecran principal. Surveillance : verification toutes les 5 s, analyse au plus '
        'toutes les 20 s, commentaire au plus une fois par minute. '
        'Images traitees localement, sans sauvegarde ; remarques vocales courtes en prive, ecrites en contexte public. '
        'Tout contenu visible sur cet ecran peut etre lu : coupe la vision avant une information privee.')


def command(text):
    normal = ''.join(c for c in unicodedata.normalize('NFD',text.lower().strip()) if unicodedata.category(c)!='Mn')
    if normal.startswith('/ecran'):
        match = re.fullmatch(r'/ecran(?: (liste|regarde|surveille|stop|etat)(?: ([1-9]))?(?:\s*\|\s*(.{1,600}))?)?',normal)
        if not match:return ('help',None,None)
        action,index,question=match.groups()
        return action,index,text.partition('|')[2].strip() if question else None
    look=re.fullmatch(r'(?:alice[, ]+)?(?:regarde|lis|decris|verifie) (?:mon |l[\x27 ])?ecran(?: ([1-9]))?(?:\s*[,;:!?]\s*(.{1,600}))?[.!?]*',normal)
    if look:return ('regarde',look[1],text[:600] if look[2] else None)
    match=re.fullmatch(r'(?:alice[, ]+)?(?:surveille|observe) (?:mon |l[\x27 ])?ecran(?: ([1-9]))?[.!?]*',normal)
    if match:return ('surveille',match[1],None)
    if normal in ('arrete de regarder mon ecran','arrete de surveiller mon ecran','coupe la vision','stop vision'):
        return ('stop',None,None)
    return None


def fingerprint(image):
    small=image.convert('L'); small.thumbnail((160,90))
    try:return (small.size,small.tobytes())
    finally:small.close()


def changed(before,after):
    if before is None or before[0]!=after[0]:return True
    a,b=before[1],after[1]
    differences=[abs(x-y) for x,y in zip(a,b)]
    return sum(differences)/max(1,len(a))>=1 or sum(v>=16 for v in differences)>=max(3,len(a)*.002)


class ScreenObserver:
    def __init__(self,session,publish,*,busy=lambda:False,capturer=capture,inventory=monitors,
                 reader=analyze,clock=time.monotonic,ocr=detect,game=game_on_monitor):
        self.session,self.publish,self.busy=session,publish,busy
        self.capture,self.inventory,self.reader,self.clock=capturer,inventory,reader,clock
        self.ocr,self.game=ocr,game
        self.deaths=DeathEvents();self.pending=None
        self.lock=threading.RLock();self.done=threading.Event();self.thread=None
        self.target=None;self.selected=None;self.generation=0
        self.previous='';self.last_fingerprint=None
        self.last_analysis=-1e9;self.last_notice=-1e9;self.last_reaction=''

    def stop(self):
        with self.lock:
            self.generation+=1;self.target=None;self.previous='';self.last_fingerprint=None
            self.last_reaction=''
            self.deaths=DeathEvents();self.pending=None

    def has_ready(self):
        with self.lock:
            if self.pending and (self.pending[0]!=self.generation or self.clock()-self.pending[1]>30 or self.target is None):
                self.pending=None
            return self.pending is not None

    def take(self):
        with self.lock:
            if not self.has_ready():return None
            value=self.pending;self.pending=None
            return value

    def close(self):
        self.stop();self.done.set()
        # Do not block the Tk shutdown. In-flight local HTTP is bounded to 45 s.

    def start(self,index):
        if not getattr(self.session,'vision_enabled',False):raise RuntimeError('Lance Alice-vision.bat pour utiliser la vision.')
        items=self.inventory()
        if not 1<=index<=len(items):raise ValueError('Cet ecran est absent. Utilise /ecran liste.')
        with self.lock:
            self.stop();self.selected=self.target=items[index-1]
            self.last_analysis=-1e9;self.last_notice=-1e9
            if self.thread is None:
                self.thread=threading.Thread(target=self._run,daemon=True,name='Alice-screen-observer')
                self.thread.start()

    def handle(self,text,source,*,cancelled=lambda:False):
        from remote_dialogue import require_local
        require_local(source)
        parsed=command(text)
        if parsed is None:raise ValueError('Commande ecran attendue.')
        action,index,question=parsed
        if action=='stop':self.stop();return 'Observation de l ecran arretee. Contexte visuel efface.'
        if action=='liste':
            return '\n'.join(f'{i}: {m.box[2]-m.box[0]} x {m.box[3]-m.box[1]}' + (' (principal)' if m.primary else '') for i,m in enumerate(self.inventory(),1))
        if action=='etat':
            with self.lock:return 'Surveillance active, observations espacees.' if self.target else 'Surveillance arretee.'
        if action=='surveille':
            if cancelled():return 'Demande annulee.'
            self.start(int(index or 1));return 'Surveillance active sur l ecran '+str(index or 1)+'. '+HELP
        if action!='regarde':return HELP
        if not getattr(self.session,'vision_enabled',False):return 'Lance Alice-vision.bat pour utiliser la vision.'
        items=self.inventory()
        number=int(index) if index else (items.index(self.selected)+1 if self.selected in items else 1)
        if not 1<=number<=len(items):return 'Cet ecran est absent. Utilise /ecran liste.'
        with self.lock:
            self.generation+=1;self.pending=None
            epoch=self.generation
        stale=lambda:cancelled() or self.done.is_set() or epoch!=self.generation
        if stale():return 'Demande annulee.'
        image=self.capture(items[number-1]);started=self.clock()
        try:value=self.reader(self.session,image,question or 'Que vois-tu ? Explique la situation utilement.',cancelled=stale)
        finally:image.close()
        if stale() or value is None or self.clock()-started>45:return 'Observation annulee ou devenue trop ancienne.'
        return ('Lecture incertaine : ' if value['uncertain'] else 'Sur cette capture : ')+value['description']+' '+value['reaction']

    def tick(self):
        with self.lock:
            target,epoch=self.target,self.generation
            if target is None or self.done.is_set() or self.busy():return
        stale=lambda:self.done.is_set() or self.generation!=epoch or self.busy()
        image=self.capture(target);started=self.clock()
        try:
            repeated=False
            if self.game(target):
                detected=self.ocr(image)
                with self.lock:
                    if stale():return
                    repeated=self.deaths.update(detected,self.clock())
            else:
                with self.lock:
                    if stale():return
                    self.deaths=DeathEvents()
            if self.clock()-self.last_analysis<20 and not repeated:return
            mark=fingerprint(image)
            if (not changed(self.last_fingerprint,mark) and not repeated) or stale():return
            question=('PASSIF : trois bannieres de mort distinctes ont ete detectees en moins de trois minutes dans un jeu au premier plan. '
                      'Si l image confirme une mort, fais UNE petite remarque sarcastique amicale, sans insulte ni jugement sur la personne. '
                      'Sinon abstiens-toi.' if repeated else 'PASSIF : signale seulement un changement utile, sans sarcasme sur une seule erreur.')
            value=self.reader(self.session,image,question,self.previous,cancelled=stale,passive=True)
        finally:image.close()
        if value is None or stale() or self.clock()-started>45:return
        with self.lock:
            if stale():return
            self.last_analysis=self.clock();self.last_fingerprint=mark
            self.previous=value['description']
            reaction=value['reaction'].strip()
            if value['notable'] and not value['uncertain'] and reaction and reaction!=self.last_reaction and self.clock()-self.last_notice>=60:
                self.last_notice=self.clock();self.last_reaction=reaction
                self.pending=(epoch,self.clock(),reaction)

    def _run(self):
        while not self.done.wait(5):
            try:self.tick()
            except Exception:
                # Stop on uncertainty of capture/transport. Never print a payload or image.
                with self.lock:
                    if self.target is not None:
                        self.stop();self.publish('Vision','Observation suspendue : capture ou analyse indisponible. /ecran surveille 1 pour reessayer.')
