"""Exact input gate in front of a scoped, freshness-checking action adapter."""
class CheckedActions:
    def __init__(self, backend, contract, before_commit=None):
        self.backend = backend
        self.contract = contract
        self.before_commit = before_commit

    def observe(self):
        return self.backend.observe()

    def act(self, action, snapshot):
        self.backend.guard()
        try:
            if type(action) is not dict:
                raise ValueError('action_schema')
            if action.get('op') in ('fill', 'select', 'check'):
                resolved = self.contract.resolve(action)
            else:
                if set(action) != {'op', 'target'} or action.get('op') != 'click':
                    raise ValueError('action_schema')
                resolved = action
            gate = None
            if resolved == {'op': 'click', 'target': 'save'}:
                # Do not reissue a snapshot here: the adapter must still reject stale intent.
                gate = self.contract.check_observation(self.backend._read())
                if not gate['ok']:
                    return {'ok': False, 'verified': False, 'reason': 'precommit_values_mismatch',
                            'gate': gate, 'dispatched': False}
                if self.before_commit is not None:
                    self.before_commit()
        except ValueError as error:
            return {'ok': False, 'verified': False, 'reason': str(error), 'dispatched': False}
        # Operational failures may occur after dispatch; never label those as a safe refusal.
        result = self.backend.act(resolved, snapshot)
        return dict(result, dispatched=True, precommit=gate)
