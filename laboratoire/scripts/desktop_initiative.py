"""Desktop adapter: explicit controls and separate public/private contexts."""
from conversation_initiative import Initiative


class DesktopInitiative:
    def __init__(self, session):
        self.core = Initiative(session)
        self.mode = 'quiet'
        self.public = []
        self.public_boundary = False
        self.last_external = []
        self._external_ids = []
        self._public_entries = []
        self._next_external_id = 0
        self.core.start()

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.core.set_mode(mode)
        self.mode = mode
        self.public = []
        self.last_external = []
        self._external_ids = []
        self._public_entries = []
        self.public_boundary = mode == 'animation'

    def _refresh_public(self, external):
        """Merge a rolling snapshot without replaying overlapping old turns.

        Source snapshots append then expire/trim from the front. Keep identities
        for their overlapping suffix, so identical text in distinct turns stays
        distinct. Only newly received turns enter the local chronology; vanished
        external turns are removed while our own delivered interventions remain.
        """
        external = [dict(message) for message in external]
        changed = external != self.last_external
        if changed:
            overlap = min(len(self.last_external), len(external))
            while overlap and self.last_external[-overlap:] != external[:overlap]:
                overlap -= 1
            retained = self._external_ids[-overlap:] if overlap else []
            new_entries = []
            for message in external[overlap:]:
                self._next_external_id += 1
                identifier = self._next_external_id
                retained.append(identifier)
                new_entries.append((identifier, message))
            live = set(retained)
            self._public_entries = [(identifier, message)
                for identifier, message in self._public_entries
                if identifier is None or identifier in live]
            self._public_entries.extend(new_entries)
            self._public_entries = self._public_entries[-12:]
            self._external_ids = retained
            self.last_external = external
        self.public[:] = [dict(message) for _, message in self._public_entries]
        return changed

    def refresh_public(self, channels=None):
        """Refresh before delivery, without rearming a user turn in progress."""
        external = channels.public_history() if channels and hasattr(channels, 'public_history') else []
        changed = self._refresh_public(external)
        if changed and (self.mode == 'animation' or
                (self.mode == 'discussion' and self.public_boundary)):
            # active() may run on the UI thread while a user types or presses
            # stop. Keep its busy guard intact until the owner calls idle().
            with self.core.lock:
                if not self.core.busy:
                    self.core.idle(self.public, public=True)
        return changed

    def active(self):
        self.core.active()

    def idle(self, history, channels=None):
        external = channels.public_history() if channels and hasattr(channels, 'public_history') else []
        self._refresh_public(external)
        if self.mode == 'animation':
            # Never pass private conversation or memory into stream animation.
            self.core.idle(self.public, public=True)
        elif self.mode == 'discussion':
            # With a public connection, use the public boundary even in discussion.
            public = bool(channels and any(channels.enabled.values()))
            if public != self.public_boundary:
                self.core.active()
            self.public_boundary = public
            self.core.idle(self.public if public else history, public=public)

    def has_ready(self):
        return self.core.has_ready()

    def deliver(self, say, history, cancelled):
        proposal = self.core.pop()
        if proposal is None or cancelled() or not self.core.valid(proposal):
            return False
        target = self.public if self.mode == 'animation' or self.public_boundary else history
        completed = say(proposal.reply)
        if completed is False:
            self.set_mode('quiet')
            return False
        if not self.core.delivered(proposal):
            return False
        target.append({'role': 'assistant', 'content': proposal.reply})
        if target is self.public:
            self._public_entries.append((None, {'role':'assistant', 'content':proposal.reply}))
            self._public_entries = self._public_entries[-12:]
            self.public[:] = self.public[-12:]
        return True

    def close(self):
        self.core.close()
        self.core.join()


MODE_COMMANDS = {
    '/initiative calme': 'quiet', '/initiative discussion': 'discussion',
    '/initiative animation': 'animation',
    'alice occupe le stream': 'animation',
    'je reviens occupe le stream': 'animation',
    'alice je reviens occupe le stream': 'animation',
    'je suis revenu': 'discussion',
    'alice reste silencieuse': 'quiet',
}


def mode_command(text):
    import re
    normalized = re.sub(r'[,!.?;:]', ' ', text.lower())
    return MODE_COMMANDS.get(' '.join(normalized.split()))
