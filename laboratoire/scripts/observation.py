"""Bounded local observation. No network, model, audio, or database access.

The writer has no action capabilities. Content is opt-in and kept only in the
current bounded snapshot, which forgetting purges synchronously.
"""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
LIVE=ROOT/'logs/observation/live.json'
LIMIT=2*1024*1024


def clean_detail(value, depth=0):
    if depth>4: return '[limite]'
    if isinstance(value,str): return value[:1500]
    if isinstance(value,dict): return {str(k)[:60]:clean_detail(v,depth+1) for k,v in list(value.items())[:12]}
    if isinstance(value,(list,tuple)): return [clean_detail(v,depth+1) for v in value[:8]]
    if value is None or type(value) in (int,bool): return value
    if type(value) is float and math.isfinite(value): return value
    return None


class Observation:
    def __init__(self, content=False, folder=None, background=True):
        if os.environ.get('PYTEST_CURRENT_TEST') and folder is None:
            raise RuntimeError('Un test doit fournir un dossier validation_ explicite')
        self.folder=Path(folder) if folder else LIVE.parent
        if folder and not self.folder.name.startswith('validation_'):
            raise ValueError('Dossier de test observation invalide')
        self.path=self.folder/'live.json'
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.events=deque(maxlen=200)
        self.active={}
        self.counters={}
        self.resource={}
        self.sequence=0
        self.turn_id=0
        self.turn_started=None
        self.speech_end=None
        self.content=bool(content)
        self.session_id=uuid.uuid4().hex
        self.started=time.time()
        self.lifecycle='starting'
        self.io_error=None
        self.thread=None
        self.emit('session.start',metrics={'content_enabled':self.content})
        self.flush()
        if background:
            self.thread=threading.Thread(target=self._writer,daemon=True)
            self.thread.start()

    def emit(self,kind,metrics=None,detail=None):
        if not re.fullmatch(r'[a-z_.]{1,60}',kind): return
        with self.lock:
            self.sequence+=1
            row={'seq':self.sequence,'at':time.time(),'turn':self.turn_id,'kind':kind}
            # Metrics must be small and explicitly supplied by instrumentation,
            # never a model response, exception message, prompt or action argument.
            safe={}
            for key,value in (metrics or {}).items():
                if not re.fullmatch(r'[a-z_]{1,60}',str(key)): continue
                if type(value) in (int,bool) or value is None: safe[key]=value
                elif type(value) is float and math.isfinite(value): safe[key]=round(value,4)
                elif isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{0,80}',value): safe[key]=value
            row['metrics']=safe
            if kind in {'voice.playback_started','voice.playback_submitted'} and self.turn_started is not None:
                safe['seconds_since_input']=round(time.monotonic()-self.turn_started,3)
                if self.speech_end is not None:
                    safe['seconds_since_vad_speech_end']=round(time.monotonic()-self.speech_end,3)
            if self.content and detail is not None: row['detail']=clean_detail(detail)
            self.events.append(row)
            self.counters[kind]=self.counters.get(kind,0)+1

    def begin_turn(self,text,source,speech_end_monotonic=None):
        with self.lock:
            self.turn_id+=1
            self.turn_started=time.monotonic()
            self.speech_end=(speech_end_monotonic if source=='voice'
                and type(speech_end_monotonic) in (int,float) and math.isfinite(speech_end_monotonic)
                and 0<=self.turn_started-speech_end_monotonic<=180 else None)
            self.emit('turn.input',{'source':source,'characters':len(text)}, {'text':text})

    @contextmanager
    def span(self,name):
        token=uuid.uuid4().hex
        start=time.monotonic()
        with self.lock:
            self.active[token]={'name':name,'start':start,'turn':self.turn_id}
        self.emit('phase.start',{'phase':name})
        try:
            yield
        except BaseException as error:
            self.emit('phase.error',{'phase':name,'error_type':type(error).__name__}, {'message':str(error)})
            raise
        finally:
            with self.lock: self.active.pop(token,None)
            self.emit('phase.end',{'phase':name,'seconds':time.monotonic()-start})

    def sample(self,**values):
        # Resources contain numeric counters and status codes, not window titles.
        with self.lock:
            self.resource.update(values)
            self.resource['at']=time.time()

    def ready(self):
        with self.lock: self.lifecycle='running'
        self.emit('session.ready')

    def purge(self, content=None):
        if self.folder.resolve() == LIVE.parent.resolve():
            from voice_capture import purge as purge_voice
            purge_voice(self.folder)
        with self.lock:
            self.events.clear()
            self.counters.clear()
            if content is not None: self.content=bool(content)
            self.emit('trace.cleared',{'content_enabled':self.content})
            # Serialize under the same lock as the writer: an old snapshot cannot
            # be published again after purge. No archive or sidecar is created.
            self.flush()
            if self.io_error:
                for path in (self.path,self.path.with_suffix('.pending')):
                    try: path.unlink(missing_ok=True)
                    except OSError: return False
            return True

    def snapshot(self):
        with self.lock:
            now=time.time()
            return {'version':1,'session':self.session_id,'started':self.started,'heartbeat':now,
                'lifecycle':self.lifecycle,'content_enabled':self.content,'turn':self.turn_id,
                'writer_error':self.io_error,'resources':dict(self.resource),
                'active':[{'phase':p['name'],'seconds':round(time.monotonic()-p['start'],3),'turn':p['turn']}
                    for p in self.active.values()],
                'counters':dict(self.counters),'events':list(self.events)}

    def flush(self):
        with self.lock:
            try:
                data=self.snapshot()
                raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
                while len(raw)>LIMIT and data['events']:
                    data['events'].pop(0)
                    raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.folder.mkdir(parents=True,exist_ok=True)
                pending=self.path.with_suffix('.pending')
                pending.write_bytes(raw)
                os.replace(pending,self.path)
                self.io_error=None
            except Exception as error:
                # Observability failure must not become an assistant failure.
                self.io_error=type(error).__name__
                try: self.path.with_suffix('.pending').unlink(missing_ok=True)
                except OSError: pass

    def _writer(self):
        while not self.stop.wait(1): self.flush()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=3)
        with self.lock: self.lifecycle='stopped'
        self.emit('session.stop')
        self.flush()


def emit(session,kind,metrics=None,detail=None):
    observer=getattr(session,'observer',None)
    if isinstance(observer,Observation): observer.emit(kind,metrics,detail)


@contextmanager
def span(session,name):
    observer=getattr(session,'observer',None)
    if isinstance(observer,Observation):
        with observer.span(name): yield
    else: yield


def purge(session):
    observer=getattr(session,'observer',None)
    if isinstance(observer,Observation): return observer.purge()
    return True


def read_snapshot(path=LIVE):
    path=Path(path)
    if path.stat().st_size>LIMIT: raise ValueError('Journal trop volumineux')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=1 or not isinstance(data.get('events'),list): raise ValueError('Journal invalide')
    return data


def assess(data,now=None):
    """Rule-based observations, never a verdict on semantic truth or audio quality."""
    now=time.time() if now is None else now
    findings=[]
    def add(level,code,text): findings.append({'level':level,'code':code,'text':text})
    age=max(0,now-data['heartbeat'])
    if data['lifecycle']=='stopped': add('info','stopped','Session terminee; ce sont les dernieres mesures.')
    elif age>5: add('warning','stale','Signal absent depuis plus de 5 s : etat actuel inconnu, pas une preuve de crash.')
    if data.get('writer_error'): add('error','writer','Le journal ne peut pas etre ecrit.')
    waiting=any(p['phase'] in ('listening','confirmation') for p in data.get('active',[]))
    for active in data.get('active',[]):
        if not waiting and active['seconds']>45:
            add('warning','slow_stage',f"Etape {active['phase']} en cours depuis {active['seconds']:.0f} s; a examiner.")
    resources=data.get('resources',{})
    if data['lifecycle']=='running' and now-resources.get('cpu_ram_at',resources.get('at',0))>20:
        add('warning','resource_stale','Mesure des ressources absente ou ancienne.')
    if resources.get('ram_free_gib',99)<6:
        if resources.get('ram_protection',True):add('error','ram','RAM sous le seuil de protection de 6 Gio.')
        else:add('warning','ram','RAM libre sous 6 Gio ; arret automatique desactive a la demande utilisateur.')
    if resources.get('guard_stopped'): add('error','guard','Une protection a arrete les moteurs : '+str(resources.get('guard_reason') or 'consulter les erreurs de session'))
    if resources.get('dead_children',0)>0 and data['lifecycle']=='running':
        add('warning','worker','Au moins un processus surveille est termine; verifier l etape et le code de sortie.')
    if resources.get('fps_protection') is False:
        text=('Protection FPS desactivee par choix utilisateur; protection RAM conservee.'
            if resources.get('ram_protection',True) else
            'Arrets automatiques FPS et RAM desactives par choix utilisateur; mesures conservees.')
        add('info','fps_disabled',text)
    elif resources.get('game_present') and not resources.get('fps_available'):
        add('warning','fps_unknown','Jeu detecte, FPS non disponibles dans cet instantane.')
    if resources.get('game_present') and resources.get('fps_at') and now-resources['fps_at']>12:
        add('warning','fps_stale','Derniers FPS trop anciens : ne pas les prendre pour une mesure actuelle.')
    if resources.get('gpu_at') and now-resources['gpu_at']>35:
        add('warning','gpu_stale','Derniere mesure GPU ancienne.')
    for event in data.get('events',[])[-50:]:
        kind=event['kind']
        if kind in ('phase.error','turn.error','session.error'):
            add('error','reported_error',f"Erreur mesuree au tour {event['turn']} : {kind}.")
        elif kind=='user.flag': add('review','user_flag',f"Probleme signale par toi au tour {event['turn']}.")
        elif kind=='memory.selected' and event['metrics'].get('selected',0)==0:
            add('review','no_source',f"Tour {event['turn']} : aucun souvenir retenu; pertinence a juger selon la demande.")
        elif kind=='model.retry': add('warning','retry',f"Tour {event['turn']} : reponse du modele retentee.")
    # Keep duplicate symptoms compact, without claiming an overall quality score.
    unique={f['code']+f['text']:f for f in findings}
    return list(unique.values())[-20:]


def format_snapshot(data):
    findings=assess(data)
    resource=data.get('resources',{})
    counts=data.get('counters',{})
    state={'starting':'chargement','running':'en cours','stopped':'terminee'}.get(data['lifecycle'],data['lifecycle'])
    if data['lifecycle']!='stopped' and time.time()-data['heartbeat']>5:
        state='signal ancien - etat actuel inconnu'
    lines=[f"Session {data['session'][:8]} | {state} | tour {data['turn']}",
        'Texte des echanges : '+('CONSERVE LOCALEMENT' if data['content_enabled'] else 'NON CONSERVE'),
        'Qualite du sens, personnalite et son : NON EVALUEE automatiquement.',
        f"RAM libre : {resource.get('ram_free_gib','?')} Gio | CPU total : {resource.get('cpu_percent','?')} % | "
        f"GPU reserve : {resource.get('gpu_used_gib','?')}/{resource.get('gpu_capacity_gib','?')} Gio (total carte)",
        f"FPS presentes / affiches : {resource.get('fps','?')} / {resource.get('displayed_fps','?')} | "
        f"Jeu au premier plan : {resource.get('game_foreground','?')}",
        'Processus : '+json.dumps(resource.get('child_states',{}),ensure_ascii=False),
        f"Session : {counts.get('model.output',0)} appels modele termines, {counts.get('model.retry',0)} reprises, "
        f"{counts.get('turn.error',0)} tours en erreur, {counts.get('session.error',0)} erreurs de session, "
        f"{counts.get('memory.written',0)} ecritures memoire.",
        'Etapes en cours : '+json.dumps(data.get('active',[]),ensure_ascii=False),
        '\nCONSTATS ET POINTS A VERIFIER']
    lines.extend(f"[{f['level']}] {f['text']}" for f in findings)
    if not findings: lines.append('Aucune anomalie detectee par ces regles; cela ne prouve pas la justesse des reponses.')
    lines.append('\nEVENEMENTS RECENTS')
    for e in data['events'][-100:]:
        stamp=datetime.fromtimestamp(e['at'],timezone.utc).strftime('%H:%M:%S')
        lines.append(f"{stamp} UTC | tour {e['turn']} | {e['kind']} | {json.dumps(e['metrics'],ensure_ascii=False)}")
        if 'detail' in e: lines.append(json.dumps(e['detail'],ensure_ascii=False))
    return '\n'.join(lines)
