"""Deliver a visual reaction without adding it to memory, diagnostic text or OBS subtitles."""
def deliver(app,text,*,passive=False,cancelled=lambda:False):
    if cancelled() or app.stop.is_set():return False
    app.events.put(('text',('Vision locale',text)))
    public=bool(app.channels and any(app.channels.enabled.values())) or bool(getattr(app.initiative,'public_boundary',False))
    if public:
        # Passive comments remain written in public mode: no repeated approval dialogs.
        if passive or not app.confirm('Dire cette observation d ecran a voix haute en contexte public ?\n\n'+text):return False
    if cancelled() or app.stop.is_set() or app.paused.is_set():return False
    voice=app.session.voice
    subtitles=getattr(voice,'subtitles',None);capture=voice.capture_allowed
    voice.subtitles=None;voice.capture_allowed=False
    try:return voice.speak(text)
    finally:voice.subtitles=subtitles;voice.capture_allowed=capture
