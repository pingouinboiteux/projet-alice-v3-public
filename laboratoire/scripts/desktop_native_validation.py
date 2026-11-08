"""Ordinary widgets + installed native boundary, only an authorized test window."""
import queue
import time
from pathlib import Path

from chat import ROOT
from desktop_native import DesktopNative, desktop_guard, run_native_turn
from native_backend_factory import NativeBackendFactory
from native_window_catalog import WindowCatalog
from native_window_focus import NativeWindowFocus
from native_typing_context import notepad_typing_context
from native_text_request import interpret
from observer_action_bench import ObserverSession
from vision_bench_runtime import save


class SilentVoice:
    def __init__(self): self.interruption_epoch=0
    def interrupt(self): self.interruption_epoch+=1
    def close(self): self.interrupt()


def run(app):
    session=ObserverSession()
    session.voice=SilentVoice()
    app.session=session
    report={'status':'starting','cases':[], 'private_memory_opened':False,
            'scope':'ordinary widgets, installed native controller, synthetic Notepad only'}
    path=ROOT/'data/validation/validation_interface_native_20261107'/('run_'+time.strftime('%H%M%S')+'.json')
    deadline=time.monotonic()+240
    def show(text):
        app.events.put(('text',('Alice',text)))
        return True
    app.say=show
    try:
        desktop_guard(session)
        catalog=WindowCatalog(['notepad.exe'])
        matches=[r for r in catalog() if r['window']['hwnd']==app.validation_native_window]
        if len(matches)!=1 or matches[0]['title'].lstrip('*') not in (
                'Sans titre – Bloc-notes','validation_texte – Bloc-notes'):
            raise RuntimeError('synthetic_notepad_window_required')
        identity=matches[0]['window']
        def components(guard):
            inventory=lambda:[r for r in catalog() if r['window']==identity]
            factory=NativeBackendFactory(catalog,guard,
                focus=NativeWindowFocus(catalog,guard),
                typing_context_factory=notepad_typing_context)
            return inventory,factory
        app.natives=DesktopNative(session,components=components)
        session.start()
        app.events.put(('status','Essai natif pret. Aucun microphone ni voix.'))
        while not app.stop.is_set():
            desktop_guard(session)
            if time.monotonic()>deadline:raise RuntimeError('native_validation_deadline')
            try:text=app.inputs.get(timeout=.2)
            except queue.Empty:continue
            app.events.put(('text',('Toi',text)))
            intent=interpret(text,'text')
            if intent['status']!='ready' or intent['target']['text']!='validation_texte':
                show('Ce banc accepte seulement la saisie exacte validation_texte dans le document fictif.')
                continue
            app.speech_epoch=session.voice.interruption_epoch
            result=run_native_turn(app,text,'text')
            report['cases'].append({'request':text,'result':result})
            save(path,report)
        report['status']='complete'
    except Exception as error:
        report.update(status='failed',error=repr(error))
        show('Essai arrete : '+str(error))
    finally:
        if getattr(app,'natives',None):app.natives.cancel()
        session.close()
        report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values())
        report['minimum_free_ram']=session.minimum_ram
        app.finished.set()
        app.observation.close()
        app.validation_folder.cleanup()
        report['observation_removed']=not Path(app.validation_folder.name).exists()
        save(path,report)
        app.events.put(('finished',None))
