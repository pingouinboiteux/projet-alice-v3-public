"""Reply delivery using the caller application state."""
def say(self, text):
    if self.session.voice.interruption_epoch != self.speech_epoch:
        return False
    self.observation.emit('turn.reply',{'characters':len(text)}, {'text':text})
    self.events.put(('text', ('Alice', text)))
    self.events.put(('status', 'Alice parle. Ecoute stop seule.' if self.stop_word_enabled.is_set() else 'Alice parle. Microphone ferme.'))
    with self.observation.span('voice_delivery'):
        voice = self.session.voice
        self.speech_epoch = voice.interruption_epoch
        voice.capture_allowed = True
        try:
            return voice.speak(text)
        finally:
            voice.capture_allowed = False
