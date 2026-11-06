"""Local speech attribution before dialogue, memory and action routing."""


def accept_speech(app, heard, history, thoughts):
    from public_scene import parse_scene_command
    try:
        if parse_scene_command(heard.get('text','')) is not None:
            # A deliberately shared local directive already names its recipient.
            return True
    except ValueError:
        pass
    public=(app.initiative.mode=='animation' or
            bool(app.channels and any(app.channels.enabled.values())))
    if not public:
        app.stream_recipient.reset()
        return True
    app.initiative.active()
    thoughts.active()
    # cleaned has removed the wake name, including from negated addresses.
    # Missing original text is not a reason to guess the recipient.
    result=app.stream_recipient.decide(app.session,heard.get('text',''))
    app.session.check()
    address=result['address']
    app.observation.emit('hearing.recipient',{'address':address})
    if address=='alice':return True
    app.events.put(('status','Parole destinée à quelqu’un d’autre : Alice laisse la place.'
                    if address=='other' else 'Destinataire incertain : Alice laisse la place.'))
    app.initiative.defer(history,app.channels,seconds=18)
    return False
