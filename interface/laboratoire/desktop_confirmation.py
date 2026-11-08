"""Tk confirmation dialog; importing this module starts no application or service."""
import time
import tkinter as tk
from tkinter import scrolledtext

ACTION_CONFIRM_SECONDS = 60
MEMORY_CONFIRM_SECONDS = 300

def confirm_details(parent,description,stop,deadline=None,*,cancelled=lambda:False):
    """Long memory previews must remain readable, cancellable and explicitly approved."""
    if deadline is None:
        deadline=time.monotonic()+(MEMORY_CONFIRM_SECONDS if len(description)>=1600 else ACTION_CONFIRM_SECONDS)
    if stop.is_set() or cancelled() or time.monotonic()>=deadline:return False
    dialog=tk.Toplevel(parent);dialog.title('Verifier avant de confirmer')
    dialog.geometry('850x650' if len(description)>=1600 else '650x300');dialog.transient(parent)
    dialog.minsize(500,260)
    text=scrolledtext.ScrolledText(dialog,wrap='word',height=6)
    text.insert('1.0',description);text.configure(state='disabled')
    result=[False];finished=[False]
    remaining=tk.StringVar(value='')
    footer=tk.Frame(dialog);footer.pack(side='bottom',fill='x')
    tk.Label(footer,textvariable=remaining).pack()
    def finish(accepted):
        if finished[0]:return
        finished[0]=True
        result[0]=accepted and not stop.is_set() and not cancelled() and time.monotonic()<deadline
        dialog.destroy()
    buttons=tk.Frame(footer);buttons.pack(pady=10)
    tk.Button(buttons,text='Annuler',command=lambda:finish(False)).pack(side='left',padx=12)
    tk.Button(buttons,text='Confirmer les changements affiches',command=lambda:finish(True)).pack(side='left',padx=12)
    text.pack(fill='both',expand=True,padx=12,pady=12)
    dialog.protocol('WM_DELETE_WINDOW',lambda:finish(False));dialog.bind('<Escape>',lambda _:finish(False))
    def check_stop():
        if stop.is_set() or cancelled() or time.monotonic()>=deadline:finish(False)
        elif dialog.winfo_exists():
            remaining.set('Sans confirmation : annulation dans '+str(max(0,int(deadline-time.monotonic())))+' s.')
            dialog.after(100,check_stop)
    dialog.grab_set();dialog.after(100,check_stop);parent.wait_window(dialog)
    return result[0] and not stop.is_set() and not cancelled()
