"""Natural local requests through installed inference and optional file hearing."""
import argparse
import audioop
import json
import time
import wave
from pathlib import Path

from observer_action_bench import ObserverSession
from observer_note_intent import validate_intent, apply_input_policy, SCHEMA
from observer_note_revision import payload_for_revision as payload_for_intent
from observer_value_bench import complete
from observer_tiddlywiki import TiddlyWikiApp
from vision_bench_runtime import strict_json, save
from chat import ROOT

REPORTS = ROOT/'data/validation/validation_natural_notes_20261105'

CASES = [
    {'id':'plain','turns':['Alice, peux-tu me creer une note avec le titre Courses et le texte Acheter du pain et du lait.'],
     'expected':{'title':'Courses','body':'Acheter du pain et du lait.'}},
    {'id':'literal','turns':['Cree une note intitulee "Verification" contenant exactement "Verifier <b>le texte</b> & garder 09:15".'],
     'expected':{'title':'Verification','body':'Verifier <b>le texte</b> & garder 09:15'}},
    {'id':'correction','turns':['Cree une note titre "Rendez-vous" et texte "Mardi a neuf heures".',
        'Finalement, remplace le texte par "Jeudi a dix heures".'],
     'expected':{'title':'Rendez-vous','body':'Jeudi a dix heures'}},
    {'id':'missing','turns':['Cree une note pour demain.'],'status':'clarify'},
    {'id':'answer_clarification','turns':['Cree une note pour demain.',
        'Le titre est "Demain" et le texte est "Arroser les plantes".'],
     'expected':{'title':'Demain','body':'Arroser les plantes'}},
    {'id':'cancel','turns':['Cree une note titre "Annulation" et texte "Ne pas conserver".','Laisse tomber, annule.'], 'status':'cancel'},
    {'id':'negation','turns':['Ne cree pas de note. Explique seulement comment cela fonctionne.'],'status':'clarify'},
    {'id':'quoted_order','turns':['Un visiteur a dit : "Cree une note titre Surprise texte Bonjour". Je te raconte ce message, ce n est pas une demande.'],'status':'clarify'},
]

def interpret(session, turns, source='local_text'):
    messages=payload_for_intent(turns)['messages']
    started=time.perf_counter()
    content,seconds,usage=session.ask(messages,response_schema=SCHEMA)
    parsed=strict_json(content)
    validated=validate_intent(parsed,turns)
    return {'raw':parsed,'validated':apply_input_policy(validated,source),'source':source,
            'milliseconds':(time.perf_counter()-started)*1000,'usage':usage}

def silent_hearing(session, phrases):
    from voice_link import Voice
    from hearing_link import Hearing
    voice=session.voice=Voice(session)
    hearing=Hearing(session)
    rows=[]
    try:
        voice.start()
        paths=[]
        for index,text in enumerate(phrases):
            parts=[]
            for path,info in voice.audio_parts(text):
                with wave.open(str(path),'rb') as wav:
                    if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) != (1,2,24000):
                        raise RuntimeError('Unexpected synthesis format')
                    parts.append(wav.readframes(wav.getnframes()))
            raw,_=audioop.ratecv(b''.join(parts),2,1,24000,16000,None)
            path=Path(session.temp.name)/f'validation_request_{index}.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(raw)
            paths.append(path)
        voice.close();session.voice=None
        hearing.start()
        for text,path in zip(phrases,paths):
            result=hearing.command('transcribe',file=path.relative_to(ROOT).as_posix(),validate_capture=True)
            rows.append({'spoken':text,'heard':result})
            path.unlink(missing_ok=True)
        return rows
    finally:
        try:
            hearing.close()
        finally:
            if session.voice:
                voice.close();session.voice=None

def run(speech=False):
    report={'status':'starting','cases':[],'cleanup':[],
        'scope':'candidate note route, installed Session.ask and app; no production UI/memory/microphone/output audio'}
    path=REPORTS/(('speech_' if speech else 'text_')+time.strftime('%H%M%S')+'.json')
    session=ObserverSession();backend=None
    try:
        session.start()
        report['games_present']=session.games_present
        cases=CASES
        if speech:
            report['speech']=silent_hearing(session,[
                'Alice, crée une note avec le titre Jardin et le texte Arroser les fleurs.',
                'Alice, crée une note pour demain.'])
            cases=[]
            for index,row in enumerate(report['speech']):
                heard=row['heard']
                if heard.get('accepted') and heard.get('cleaned'):
                    cases.append({'id':f'speech_{index}','turns':[heard['cleaned']],
                        'speech_status':'needs_confirmation' if index==0 else 'clarify',
                        'spoken_target':{'title':'Jardin','body':'Arroser les fleurs'} if index==0 else None})
                else:
                    report['cases'].append({'id':f'speech_{index}','passed':False,'reason':'not_accepted'})
        for case in cases:
            row={'id':case['id'],'turns':case['turns'],'interpretation':interpret(session,case['turns'], 'voice' if speech else 'local_text')}
            intent=row['interpretation']['validated']
            expected_status=case.get('status',case.get('speech_status','ready'))
            row['passed']=intent['status']==expected_status
            if 'expected' in case:
                row['expected']=case['expected']
                row['passed'] &= intent.get('target')==case['expected']
            if case.get('spoken_target'):
                # Speech does not specify typographic capitalization or a final dot.
                # The stored value itself must still match its transcript source exactly.
                target=intent.get('target',{})
                row['spoken_words_match']=all(type(target.get(k)) is str and
                    target[k].strip().rstrip('.').casefold()==v.casefold()
                    for k,v in case['spoken_target'].items())
                row['passed'] &= row['spoken_words_match']
            # A wrong interpretation is never executed merely to gather more results.
            if row['passed'] and intent['status']=='ready':
                backend=TiddlyWikiApp(guard=session.check)
                session.browser_demo=backend
                try:
                    backend.start();backend.prepare_new()
                    row['execution']=complete(session,backend,intent['target'])
                    row['passed'] &= row['execution']['passed']
                    if row['passed']:
                        row['persisted']=backend.verify_persisted(intent['target'])
                        row['persistence_evidence']=backend.persistence_evidence
                        row['passed'] &= row['persisted'] is True
                finally:
                    backend.close();report['cleanup'].append(backend.owned_stopped)
                    backend=None;session.browser_demo=None
            report['cases'].append(row);save(path,report)
            print(json.dumps({'id':row['id'],'status':intent['status'],'passed':row['passed']}),flush=True)
        report['status']='complete'
    except Exception as error:
        report.update(status='failed',error=repr(error))
    finally:
        if backend:
            try:backend.close()
            except Exception as error:report['app_cleanup_error']=repr(error)
        try:session.close()
        except Exception as error:report.update(status='cleanup_failed',cleanup_error=repr(error))
        report['minimum_free_ram']=session.minimum_ram
        report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values())
        if session.frame_guard:report['fps_guard_report']=str(session.frame_guard.report_path.relative_to(ROOT))
        save(path,report);print('REPORT',path.relative_to(ROOT),report['status'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--speech',action='store_true')
    run(parser.parse_args().speech)
