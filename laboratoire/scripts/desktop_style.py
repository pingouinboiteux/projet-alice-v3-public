"""Presentation only: existing controller owns all actions and lifecycle."""
import tkinter as tk
from tkinter import scrolledtext
import os

BG='#080f17'
PANEL='#101d29'
TEXT='#e4edf5'
MUTED='#9cb1c4'
ACCENT='#58dfc2'
LINE='#244052'

def label(parent,text='',**kwargs):
    return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=TEXT,font=('Segoe UI',10),**kwargs)

def button(parent,text,command,accent=False):
    return tk.Button(parent,text=text,command=command,font=('Segoe UI',10),
        bg=ACCENT if accent else '#1b3041',fg=BG if accent else TEXT,
        activebackground='#86efda' if accent else '#29485f',activeforeground=BG if accent else TEXT,
        relief='flat',bd=0,padx=12,pady=8,cursor='hand2',
        highlightthickness=1,highlightbackground=LINE,highlightcolor=ACCENT)

def build(app,root):
    window=app.window
    window.title('Alice | Laboratoire local')
    window.geometry('1060x800');window.minsize(920,720);window.configure(bg=BG)
    app.status=tk.StringVar(master=window,value='Chargement. Le microphone est ferme.')
    app.resources=tk.StringVar(master=window,value='Surveillance des ressources en preparation.')
    app.diagnostic_enabled=tk.BooleanVar(master=window,value='--diagnostic' in __import__('sys').argv)
    app.observation_status=tk.StringVar(master=window,value='Observation locale; aucun envoi externe.')
    app.external_status=tk.StringVar(master=window,value='Twitch et Discord : coupes.')
    app.external_states={'twitch':'coupe','discord':'coupe'}

    top=tk.Frame(window,bg=BG);top.pack(fill='x',padx=24,pady=(18,12))
    title=label(top,'A L I C E');title.configure(font=('Segoe UI Semibold',22),fg=ACCENT);title.pack(side='left')
    label(top,'LABORATOIRE  /  ASSISTANTE LOCALE').pack(side='left',padx=20)
    button(top,'Arrêter Alice · F12',app.shutdown).pack(side='right')
    body=tk.Frame(window,bg=BG);body.pack(fill='both',expand=True,padx=24,pady=(0,20))
    sidebar=tk.Frame(body,bg=PANEL,width=266);sidebar.pack(side='right',fill='y',padx=(18,0));sidebar.pack_propagate(False)
    main=tk.Frame(body,bg=BG);main.pack(side='left',fill='both',expand=True)

    hero=tk.Frame(main,bg=BG);hero.pack(fill='x',pady=(0,12))
    orb=tk.Canvas(hero,width=120,height=120,bg=BG,highlightthickness=0);orb.pack(side='left',padx=(0,16))
    orb.create_oval(7,7,113,113,outline=LINE,width=1)
    orb.create_arc(15,15,105,105,start=20,extent=250,style='arc',outline=ACCENT,width=2)
    orb.create_arc(23,23,97,97,start=210,extent=100,style='arc',outline='#5c9ee5',width=2)
    orb.create_oval(32,32,88,88,fill='#123a3e',outline=ACCENT,width=2)
    orb.create_text(60,60,text='A',fill=ACCENT,font=('Segoe UI Light',22))
    info=tk.Frame(hero,bg=BG);info.pack(side='left',fill='both',expand=True)
    label(info,'ÉTAT DE LA SESSION',anchor='w').pack(fill='x',pady=(20,6))
    status=label(info,textvariable=app.status,anchor='w',justify='left',wraplength=425)
    status.configure(fg=ACCENT,font=('Segoe UI',11));status.pack(fill='x')
    info.bind('<Configure>',lambda e:status.configure(wraplength=max(100,e.width-8)))

    label(main,'CONVERSATION',anchor='w').pack(fill='x',pady=(0,10))
    app.history=scrolledtext.ScrolledText(main,wrap='word',height=8,state='disabled',font=('Segoe UI',11),
        bg=BG,fg=TEXT,insertbackground=ACCENT,selectbackground='#285b70',relief='flat',bd=0,
        padx=16,pady=12,highlightthickness=1,highlightbackground=LINE)
    app.history.pack(fill='both',expand=True)
    app.history.vbar.configure(bg=PANEL,troughcolor=BG,activebackground=LINE)
    for name,color,left,right in [('alice','#132631',12,55),('self','#173d48',55,12),('system','#1c2633',12,12)]:
        app.history.tag_configure(name,background=color,lmargin1=left,lmargin2=left,rmargin=right,
            spacing1=8,spacing3=10,foreground=TEXT)
    app.history.tag_configure('speaker',font=('Segoe UI Semibold',9),foreground=ACCENT)
    composer=tk.Frame(main,bg=PANEL,padx=10,pady=10);composer.pack(fill='x',pady=(12,8))
    button(composer,'Envoyer',app.submit,accent=True).pack(side='right',padx=(10,0))
    app.entry=tk.Entry(composer,font=('Segoe UI',12),bg=PANEL,fg=TEXT,insertbackground=ACCENT,
        relief='flat',selectbackground='#285b70')
    app.entry.pack(side='left',fill='x',expand=True,ipady=9)
    app.entry.bind('<Return>',app.submit)
    label(main,'Écris ici, ou dis « Alice » puis ta demande.',anchor='w').pack(fill='x')
    controls=tk.Frame(main,bg=BG);controls.pack(fill='x',pady=(10,0))
    app.pause_button=button(controls,'Couper le micro',app.toggle_pause);app.pause_button.pack(side='left')
    button(controls,'Nouvelle discussion',lambda:app.inputs.put('/nouveau')).pack(side='left',padx=8)

    def section(title):
        frame=tk.Frame(sidebar,bg=PANEL);frame.pack(fill='x',padx=16,pady=(16,0))
        heading=label(frame,title,anchor='w');heading.configure(fg=ACCENT,font=('Segoe UI Semibold',10));heading.pack(fill='x',pady=(0,8))
        return frame
    def wrapped(parent,variable):
        item=label(parent,textvariable=variable,wraplength=228,justify='left',anchor='w');item.configure(fg=MUTED,font=('Segoe UI',9));item.pack(fill='x',pady=(6,0))
    frame=section('CONNEXIONS')
    for source in ('twitch','discord'):
        button(frame,'Connecter / couper '+source.title(),lambda s=source:app.channel_command(s)).pack(fill='x',pady=2)
    wrapped(frame,app.external_status)
    frame=section('MÉMOIRE & ATELIER')
    row=tk.Frame(frame,bg=PANEL);row.pack(fill='x')
    button(row,'Souvenirs',lambda:app.inputs.put('/memoire')).pack(side='left')
    button(row,'Tout oublier',lambda:app.inputs.put('/oublier-tout')).pack(side='right')
    button(frame,"Ouvrir l’atelier",lambda:os.startfile(root/'atelier')).pack(fill='x',pady=(6,0))
    frame=section('RESSOURCES')
    wrapped(frame,app.resources)
    frame=section('OBSERVATION')
    button(frame,'Ouvrir la surveillance',app.open_observation).pack(fill='x')
    row=tk.Frame(frame,bg=PANEL);row.pack(fill='x',pady=6)
    button(row,'Signaler',lambda:app.observation.emit('user.flag')).pack(side='left')
    button(row,'Effacer le journal',app.observation.purge).pack(side='right')
    tk.Checkbutton(frame,text='Diagnostic avec textes locaux',variable=app.diagnostic_enabled,
        command=app.toggle_diagnostic,bg=PANEL,fg=TEXT,selectcolor=BG,activebackground=PANEL,
        activeforeground=TEXT,font=('Segoe UI',9),wraplength=220,anchor='w').pack(fill='x')
    wrapped(frame,app.observation_status)

def append(app,speaker,text):
    history=app.history
    follow=history.yview()[1]>=0.98
    tag='self' if speaker=='Toi' else 'alice' if speaker=='Alice' else 'system'
    history.configure(state='normal')
    history.insert('end',speaker.upper()+'\n',(tag,'speaker'))
    history.insert('end',text+'\n',tag)
    history.insert('end','\n')
    count=int(history.count('1.0','end','chars')[0])
    if count>150000:history.delete('1.0',f'1.0+{count-120000}c')
    if follow:history.see('end')
    history.configure(state='disabled')
