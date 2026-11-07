"""Pure selection over a trusted inventory; never selects the first match."""
from copy import deepcopy


def select_window(candidates, hint, *, allowed_processes):
    if type(hint) is not str or not hint.strip():
        raise ValueError('native_window_hint_required')
    hint=hint.strip().casefold()
    allowed={name.casefold() for name in allowed_processes}
    matches=[]
    for item in candidates:
        name=item.get('process_name','').casefold()
        title=item.get('title','').strip().casefold()
        named=(title==hint or (hint in ('bloc-notes','bloc notes') and name=='notepad.exe'))
        if named and name in allowed and item.get('visible') is True:
            matches.append(item)
    if len(matches)!=1:
        raise ValueError('native_window_missing_or_ambiguous')
    return deepcopy(matches[0])


def select_text_control(snapshot, text):
    if snapshot.get('truncated') is not False:
        raise ValueError('native_selection_incomplete')
    if snapshot.get('foreground') is not True or snapshot.get('available') is not True:
        raise ValueError('native_selection_window_not_ready')
    candidates=[e for e in snapshot['elements']
        if e.get('type') in ('ControlType.Edit','ControlType.Document')
        and e.get('editable') is True and e.get('password') is False
        and e.get('visible') is True and e.get('enabled') is True]
    # A focused search field is not enough evidence of being the intended body.
    if len(candidates)!=1:
        raise ValueError('native_text_control_missing_or_ambiguous')
    target=candidates[0]
    if target.get('value') not in ('',text):
        raise ValueError('native_existing_text_needs_explicit_revision')
    return target['id']
