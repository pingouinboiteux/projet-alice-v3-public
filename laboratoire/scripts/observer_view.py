"""Read-only local viewer and bounded CLI for Codex/live diagnosis."""
import argparse
import json
import time
from observation import read_snapshot, format_snapshot, assess


def open_window(parent=None,path=None):
    import tkinter as tk
    from tkinter import scrolledtext
    window=tk.Toplevel(parent) if parent else tk.Tk()
    window.title('Observation Alice - lecture seule')
    window.geometry('1000x720')
    tk.Label(window,text='Lecture seule, actualisation 1 s. Aucun modele supplementaire. '
        'Le texte est disponible seulement en mode diagnostic.',wraplength=960).pack(padx=10,pady=8)
    text=scrolledtext.ScrolledText(window,wrap='word',font=('Consolas',10),state='disabled')
    text.pack(fill='both',expand=True,padx=10,pady=8)
    closed=False
    def close():
        nonlocal closed
        closed=True;window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def refresh():
        if closed: return
        try: value=format_snapshot(read_snapshot(path) if path else read_snapshot())
        except FileNotFoundError: value='Aucune session observee. Lance Alice-Diagnostic.bat pour un essai avec le texte des echanges.'
        except (OSError,ValueError,KeyError,TypeError) as error: value='Observation indisponible : '+type(error).__name__
        position=text.yview()[0]
        text.configure(state='normal');text.delete('1.0','end');text.insert('end',value)
        text.configure(state='disabled');text.yview_moveto(position)
        window.after(1000,refresh)
    refresh()
    if not parent: window.mainloop()
    return window


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--watch-seconds',type=int,default=0)
    args=parser.parse_args()
    if not 0<=args.watch_seconds<=60: parser.error('Observation bornee a 60 secondes par appel')
    if args.once or args.watch_seconds:
        deadline=time.monotonic()+args.watch_seconds
        previous=None
        while True:
            try:
                data=read_snapshot()
                summary={k:data[k] for k in ('session','lifecycle','content_enabled','turn','active','resources','writer_error')}
                summary['findings']=assess(data)
                salient={'turn.input','turn.reply','turn.error','session.error','hearing.result',
                    'memory.selected','memory.written','memory.extraction','memory.state','memory.forgotten',
                    'action.proposed','action.result','confirmation.result','model.retry','phase.error',
                    'user.flag','trace.cleared','voice.audio','voice.playback_started',
                    'voice.playback_submitted'}
                summary['recent_events']=[e for e in data['events'] if e['kind'] in salient][-32:]
                serialized=json.dumps(summary,ensure_ascii=True)
            except (OSError,ValueError,KeyError,TypeError) as error:
                serialized=json.dumps({'observation':'unavailable','error_type':type(error).__name__})
            if serialized!=previous: print(serialized,flush=True);previous=serialized
            if time.monotonic()>=deadline: break
            time.sleep(min(1,max(0,deadline-time.monotonic())))
    else: open_window()


if __name__=='__main__': main()
