"""Opt-in notes validation using the ordinary desktop widgets, never real memory."""
import ctypes
from ctypes import wintypes
import queue
import time
import tkinter as tk

from chat import ROOT
from observer_action_bench import ObserverSession
from observer_natural_bench import interpret
from observer_note_pending import PendingNoteReview
from observer_tiddlywiki import TiddlyWikiApp
from observer_value_bench import complete
from vision_bench_runtime import save


def configure_window(app):
    app.window.title('Alice | Validation notes temporaires')
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
                if child.cget('text') not in ('Envoyer','Arrêter Alice · F12'):
                    child.configure(state='disabled')
            disable(child)
    disable(app.window)
    app.paused.set()
    app.append('Validation','Notes temporaires uniquement. Micro, voix, souvenirs et connexions coupés. '
               'Décris une note avec son titre et son texte. Annule l’aperçu pour corriger ta demande.')


def commit_review(app,pending,authorization):
    if app.stop.is_set() or not app.inputs.empty():
        pending.cancel()
        raise ValueError('request_interrupted')
    return pending.claim(authorization)


def run(app):
    session=ObserverSession();app.session=session
    pending=app.note_pending=PendingNoteReview()
    report={'status':'starting','cases':[], 'cleanup':[], 'scope':'ordinary desktop widgets; isolated notes worker; no memory/audio/channels'}
    path=ROOT/'data/validation/validation_interface_notes_20261105'/('run_'+time.strftime('%H%M%S')+'.json')
    turns=[];backend=None
    def show(text):app.events.put(('text',('Alice',text)))
    try:
        session.start();report['games_present']=session.games_present
        app.events.put(('status','Essai notes prêt. Micro et voix coupés.'))
        while not app.stop.is_set():
            session.check()
            try:text=app.inputs.get(timeout=.2)
            except queue.Empty:continue
            app.events.put(('text',('Toi',text)))
            if text.startswith('/'):
                turns=[];pending.cancel();show('Ce mode accepte seulement des demandes de notes temporaires.');continue
            turns=(turns+[text])[-8:]
            row={'turns':list(turns)}
            try:
                intent=interpret(session,turns)['validated'];row['intent']=intent
                if intent['status']=='cancel':
                    turns=[];pending.cancel();show('Demande annulée. Aucune note enregistrée.')
                elif intent['status']!='ready':
                    show('Précise le titre et le texte exacts de la note, ou la correction souhaitée.')
                else:
                    pending.propose(intent['target'],source='local_text');review=pending.review()
                    target=review['target']
                    description=('Note temporaire — vérifie chaque valeur.\n\nTitre : '+target['title']+
                        '\n\nTexte :\n'+target['body']+'\n\nAnnuler permet de revenir au dialogue pour corriger.')
                    accepted=app.confirm(description);row['confirmed']=accepted
                    if not accepted:
                        pending.cancel();show('Rien enregistré. Tu peux corriger ta demande.');row['saved']=False
                    else:
                        authorization=pending.confirm(review['ticket'],'oui')
                        backend=TiddlyWikiApp(guard=session.check);session.browser_demo=backend
                        backend.start();backend.prepare_new()
                        outcome=complete(session,backend,target,
                            before_commit=lambda:commit_review(app,pending,authorization))
                        row['execution']=outcome
                        row['saved']=bool(outcome['passed'] and backend.verify_persisted(target))
                        row['persistence']=backend.persistence_evidence if row['saved'] else None
                        show(('Note enregistrée et relue : '+target['title']+'\n'+target['body']) if row['saved']
                             else 'Enregistrement non validé. Aucun succès annoncé.')
                        turns=[]
            except Exception as error:
                row['error']=repr(error);pending.cancel();turns=[]
                show('Essai interrompu : '+type(error).__name__+'. Aucun succès annoncé.')
            finally:
                if backend:
                    backend.close();report['cleanup'].append(backend.owned_stopped)
                    backend=None;session.browser_demo=None
                report['cases'].append(row);save(path,report)
        report['status']='complete'
    except Exception as error:
        report.update(status='failed',error=repr(error));show('Arrêt de protection : '+str(error))
    finally:
        pending.cancel()
        try:session.close()
        except Exception as error:report.update(status='cleanup_failed',cleanup_error=repr(error))
        report['minimum_free_ram']=session.minimum_ram
        report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values())
        app.finished.set();app.observation.close()
        app.validation_folder.cleanup()
        report['observation_removed']=not __import__('pathlib').Path(app.validation_folder.name).exists()
        save(path,report);app.events.put(('finished',None))
