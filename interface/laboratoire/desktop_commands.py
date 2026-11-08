"""UI callbacks and event dispatch, sharing the caller application state.

Shutdown and speech interruption remain owned by the entry point.
Platform and confirmation dependencies are supplied by that caller.
"""
import queue


def initiative_mode(self, mode):
    if mode == 'calme': self.interrupt_speech()
    self.inputs.put("/initiative " + mode)
    if self.initiative: self.initiative.active()
    if self.hearing: self.hearing.cancel()



def toggle_stop_word(self):
    if self.stop_checked.get():
        self.stop_word_enabled.set()
        self.stop_status.set('Stop vocal : arme pour la prochaine reponse')
    else:
        self.stop_word_enabled.clear()
        self.stop_status.set('Stop vocal : desactive')



def open_observation(self):
    from observer_view import open_window
    open_window(self.window)



def channel_command(self,source):
    self.channel_commands.put(source)
    if self.hearing: self.hearing.cancel()



def toggle_diagnostic(self):
    self.observation.purge(content=self.diagnostic_enabled.get())



def append(self, speaker, text):
    from desktop_style import append
    append(self, speaker, text)



def submit(self, _event=None):
    text = self.entry.get().strip()
    if text and not self.stop.is_set():
        pending=getattr(self,'note_pending',None)
        if pending: pending.cancel()
        if self.initiative: self.initiative.active()
        self.inputs.put(text[:5000])
        self.entry.delete(0, 'end')
        if self.hearing:
            self.hearing.cancel()



def toggle_pause(self):
    if self.initiative: self.initiative.set_mode("quiet")
    if self.paused.is_set():
        self.paused.clear()
        self.pause_button.configure(text='Couper le micro')
    else:
        self.paused.set()
        self.pause_button.configure(text='Reprendre le micro')
        if self.hearing:
            self.hearing.cancel()
        self.status.set('Coupure du micro demandee...')
    self.observation.emit('hearing.pause',{'paused':self.paused.is_set()})



def confirm(self, description, threading, time, MEMORY_CONFIRM_SECONDS, ACTION_CONFIRM_SECONDS):
    event, result = threading.Event(), []
    deadline=time.monotonic()+(MEMORY_CONFIRM_SECONDS if len(description)>=1600 else ACTION_CONFIRM_SECONDS)
    def invalidated():
        channel_queue=getattr(self,'channel_commands',None)
        return (self.stop.is_set() or not self.inputs.empty()
                or (channel_queue is not None and not channel_queue.empty()))
    self.events.put(('confirm', (description, event, result,deadline)))
    with self.observation.span('confirmation'):
        self.observation.emit('confirmation.request',detail={'description':description})
        while not event.wait(.1):
            if invalidated() or time.monotonic()>=deadline:
                event.set();break
            # Do not enter another conversation/confirmation while this exact
            # action is awaiting review. Incoming requests remain queued.
        accepted=bool(result and result[0]) and not invalidated() and time.monotonic()<deadline
        self.observation.emit('confirmation.result',{'accepted':accepted,'expired':time.monotonic()>=deadline})
        return accepted



def poll(self, ctypes, confirm_details):
    if self.observation.io_error:
        self.observation_status.set('ATTENTION : journal indisponible ('+self.observation.io_error+').')
    else:
        self.observation_status.set('Diagnostic avec texte local actif.' if self.diagnostic_enabled.get()
            else 'Suivi technique actif, sans texte des conversations.')
    if ctypes.windll.user32.GetAsyncKeyState(0x7B) & 0x8000:
        self.shutdown()
    try:
        while True:
            kind, value = self.events.get_nowait()
            if kind == 'text':
                self.append(*value)
            elif kind == 'clear_history':
                self.history.configure(state='normal')
                self.history.delete('1.0', 'end')
                self.history.configure(state='disabled')
            elif kind == 'status' and not self.stop.is_set():
                self.status.set(value)
            elif kind == 'stop_status':
                labels = {'requested':'ecoute demandee', 'idle':'aucun mot detecte',
                    'ignored':'parole detectee, commande non reconnue',
                    'stop':'STOP reconnu', 'error':'ERREUR ecoute : utiliser le bouton'}
                self.stop_status.set('Stop vocal : ' + labels.get(value, value))
            elif kind == 'resources':
                self.resources.set(value)
            elif kind == 'remote_status':
                source,state=value
                labels={'ready':'connecte','off':'coupe','connecting':'connexion...',
                    'not_configured':'acces absent du coffre','disconnected':'deconnecte',
                    'queue_full':'trop de messages, surplus ignore','reply_cancelled':'reponse differee'}
                self.external_states[source]=labels.get(state,'erreur')
                self.external_status.set(' | '.join(k.title()+' : '+v for k,v in self.external_states.items())+
                    '. Aucun droit d action. Casque conseille contre les retours micro.')
            elif kind == 'pause':
                self.paused.set()
                self.pause_button.configure(text='Reprendre le micro')
            elif kind == 'confirm':
                description, event, result,deadline = value
                if event.is_set():continue
                self.confirmations.append((event, result))
                accepted = False if self.stop.is_set() else confirm_details(
                    self.window,description,self.stop,deadline,cancelled=event.is_set)
                if not event.is_set():
                    result.append(accepted)
                    event.set()
                self.confirmations.remove((event, result))
            elif kind == 'finished':
                self.status.set('Alice est arretee. Tu peux fermer cette fenetre.')
    except queue.Empty:
        pass
    if self.stop.is_set() and self.finished.is_set():
        self.window.destroy()
    else:
        self.window.after(100, self.poll)
