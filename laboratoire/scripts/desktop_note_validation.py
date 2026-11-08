"""Opt-in notes validation using the ordinary desktop widgets, never real memory."""
import ctypes
from ctypes import wintypes
import queue
import time
import tkinter as tk

from chat import ROOT
from observer_action_bench import ObserverSession
from observer_note_pending import PendingNoteReview
from observer_tiddlywiki import TiddlyWikiApp
from vision_bench_runtime import save


def configure_window(app, kind='notes'):
    app.window.title('Alice | Validation native fictive' if kind=='native' else 'Alice | Validation notes temporaires')
    # Place this app's own window on a secondary monitor when one is present.
    class Info(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('monitor',wintypes.RECT),
                  ('work',wintypes.RECT),('flags',wintypes.DWORD)]
    monitors=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,
                                   ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    def collect(handle,dc,rect,data):
        info=Info();info.cbSize=ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(handle,ctypes.byref(info)) and not info.flags & 1:
            monitors.append((info.work.left,info.work.top))
        return True
    callback=callback_type(collect)
    ctypes.windll.user32.EnumDisplayMonitors(None,None,callback,0)
    if monitors:
        x,y=monitors[0]
        app.window.geometry(f'1060x800+{x+30}+{y+30}')
    def disable(widget):
        for child in widget.winfo_children():
            if isinstance(child,(tk.Button,tk.Checkbutton)):
                allowed=('Envoyer','Arrêter Alice · F12','Stop parole') if kind=='native' else ('Envoyer','Arrêter Alice · F12')
                if child.cget('text') not in allowed:
                    child.configure(state='disabled')
            disable(child)
    disable(app.window)
    app.paused.set()
    app.append('Validation',
        'Document fictif uniquement : validation_texte. Micro, voix, souvenirs et connexions coupes. Stop parole interrompt aussi la saisie.'
        if kind=='native' else
        'Notes temporaires uniquement. Micro, voix, souvenirs et connexions coupés. '
        'Décris une note avec son titre et son texte. Annule l’aperçu pour corriger ta demande.')


def commit_review(app,pending,authorization):
    if app.stop.is_set() or not app.inputs.empty():
        pending.cancel()
        raise ValueError('request_interrupted')
    return pending.claim(authorization)


def run(app):
    from pathlib import Path
    from notes_dialogue import NotesDialogue
    from notes_storage import NotesStorage
    session=ObserverSession();app.session=session
    backends=[]
    report={'status':'starting','cases':[],
            'scope':'ordinary widgets and installed NotesDialogue; synthetic storage; no memory/audio/channels'}
    path=ROOT/'data/validation/validation_interface_notes_20261106'/('run_'+time.strftime('%H%M%S')+'.json')
    storage=Path(app.validation_folder.name)/'wiki'
    def factory(guard):
        backend=TiddlyWikiApp(guard,storage=NotesStorage.validation(storage))
        session.browser_demo=backend;backends.append(backend)
        return backend
    controller=NotesDialogue(session,factory=factory)
    app.note_pending=controller.pending
    def show(text):app.events.put(('text',('Alice',text)))
    try:
        session.start();report['games_present']=session.games_present
        app.events.put(('status','Essai notes pret. Micro et voix coupes.'))
        while not app.stop.is_set():
            session.check()
            try:text=app.inputs.get(timeout=.2)
            except queue.Empty:continue
            app.events.put(('text',('Toi',text)))
            if not controller.can_handle(text):
                controller.cancel();show('Ce mode accepte seulement des demandes de notes temporaires.');continue
            row={'text':text,'confirmations':[]}
            def confirm(description):
                accepted=app.confirm(description)
                row['confirmations'].append({'preview':description,'accepted':accepted})
                return accepted
            result=controller.handle(text,'text',confirm,
                cancelled=lambda:app.stop.is_set() or not app.inputs.empty())
            row['result']=result;report['cases'].append(row)
            show(result['reply']);save(path,report)
        report['status']='complete'
    except Exception as error:
        report.update(status='failed',error=repr(error));show('Arret de protection : '+str(error))
    finally:
        controller.cancel()
        try:session.close()
        except Exception as error:report.update(status='cleanup_failed',cleanup_error=repr(error))
        report['minimum_free_ram']=session.minimum_ram
        report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values()) and all(b.owned_stopped for b in backends)
        app.finished.set();app.observation.close()
        app.validation_folder.cleanup()
        report['observation_removed']=not Path(app.validation_folder.name).exists()
        save(path,report);app.events.put(('finished',None))
