"""Candidate prompt: expose existing provenance constraints before extraction.

This does not replace validate_intent, infer field values or authorize actions.
It makes that validator's conservative lexical correction rules visible to the
model, keeping all original user turns intact for semantic interpretation.
"""
from __future__ import annotations
import json

from observer_note_intent import (
    SCHEMA, _turns, _CREATE, _CANCEL, _CORRECTION, _FIELD, payload_for_intent,
)


def revision_state(turns):
    source = _turns(turns)
    last_cancel = max((i for i, text in enumerate(source) if _CANCEL.search(text)), default=-1)
    requests = [i for i, text in enumerate(source) if i > last_cancel and _CREATE.search(text)]
    request_turn = requests[-1] if requests else None
    fields = {}
    for field in ('title', 'body'):
        minimum = request_turn
        invalidations = []
        if minimum is not None:
            for index in range(minimum + 1, len(source)):
                text = source[index]
                if not _CORRECTION.search(text):
                    continue
                named = [name for name, pattern in _FIELD.items() if pattern.search(text)]
                if not named or field in named:
                    minimum = index
                    invalidations.append(index)
        fields[field] = {
            'eligible_source_turns': list(range(minimum, len(source))) if minimum is not None else [],
            'correction_turns': invalidations,
            'must_reextract_after_correction': bool(invalidations),
        }
    return {
        'latest_user_turn': len(source) - 1,
        'active_creation_turn': request_turn,
        'latest_cancellation_turn': last_cancel if last_cancel >= 0 else None,
        'fields': fields,
        'scope': 'provenance constraints only; not extracted values or action authorization',
    }


def payload_for_revision(turns):
    payload = payload_for_intent(turns)
    state = revision_state(turns)
    payload['messages'][0]['content'] += (
        ' Etat courant fourni : pour chaque champ, eligible_source_turns indique les '
        'messages dont une citation pourrait encore etre valide. Les anciennes '
        'valeurs des champs corriges ne sont plus une proposition valable. '
        'Reextrais ces champs dans les messages indiques, meme si la premiere '
        'demande etait complete. Garde les autres champs si leur source reste valide. '
        'Ces indices ne fournissent aucune valeur : verifie le sens de tous les '
        'messages et cite exactement la valeur demandee. Une liste de sources '
        'autorisables ne prouve pas qu une valeur y est presente. Si elle manque '
        'ou si la correction est ambigue, choisis clarify. Ne reviens jamais a '
        'une ancienne valeur simplement parce que la correction est incomplete.')
    original = json.loads(payload['messages'][1]['content'])
    payload['messages'][1]['content'] = json.dumps(
        {'current_request_state': state, **original}, ensure_ascii=False)
    return payload
