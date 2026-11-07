"""Trusted opt-in projection for a tabbed text editor during its own typing.

Only the active tab's presentation and the window caption may change. The tab
identity/selection, editor, geometry and every unrelated control stay checked.
No policy is inferred from the model or from instructions in displayed text.
"""
from copy import deepcopy
import re


class TabbedTypingContext:
    def __init__(self, snapshot, target, *, passive_metrics=()):
        by_id = {e['id']: e for e in snapshot['elements']}
        selected = [e for e in by_id.values()
                    if e.get('type') == 'ControlType.TabItem' and e.get('selected') is True]
        roots = [e for e in by_id.values() if e.get('parent_id') is None
                 and e.get('type') == 'ControlType.Window']
        if len(selected) != 1 or len(roots) != 1 or target not in by_id:
            raise ValueError('native_document_anchor_required')
        if by_id[target].get('type') not in ('ControlType.Edit', 'ControlType.Document'):
            raise ValueError('native_text_target_required')
        self.tab, self.root, self.target = selected[0]['id'], roots[0]['id'], target
        self.metrics = frozenset(passive_metrics)
        for identity in self.metrics:
            element = by_id.get(identity, {})
            parent = by_id.get(element.get('parent_id'), {})
            if (element.get('type') != 'ControlType.Text' or element.get('editable') is not False
                    or element.get('password') is not False or parent.get('enabled') is not False
                    or parent.get('type') != 'ControlType.Pane'):
                raise ValueError('native_passive_metric_required')

    def project(self, snapshot):
        result = deepcopy(snapshot)
        by_id = {e['id']: e for e in result['elements']}
        selected = [e['id'] for e in by_id.values()
                    if e.get('type') == 'ControlType.TabItem' and e.get('selected') is True]
        if selected != [self.tab] or self.root not in by_id or self.target not in by_id:
            raise RuntimeError('native_active_document_changed')
        def under_tab(element):
            parent = element.get('parent_id')
            seen = set()
            while parent in by_id and parent not in seen:
                if parent == self.tab:
                    return True
                seen.add(parent)
                parent = by_id[parent].get('parent_id')
            return False
        if under_tab(by_id[self.target]):
            raise RuntimeError('native_editor_inside_tab_presentation')
        result['elements'] = [e for e in result['elements'] if not under_tab(e)]
        # Preserve tab identity, selected state, bounds, visibility and ancestry.
        for identity in (self.tab, self.root):
            by_id[identity]['name'] = ''
            by_id[identity]['value'] = None
        for identity in self.metrics:
            if identity not in by_id:
                raise RuntimeError('native_passive_metric_missing')
            element = by_id[identity]
            element['name'] = ''
            element['value'] = None
            # Text glyph bounds vary with the digits; position/height stay fixed.
            element['rect'][2] = 0
        return result


def notepad_typing_context(snapshot, target):
    """Qualified French Notepad presentation; absent matches stay strict."""
    metrics = []
    for element in snapshot['elements']:
        name = element.get('name', '')
        if (re.fullmatch(r'\d+ caract[eè]res?', name)
                or re.fullmatch(r'Ligne \d+, colonne\s+\d+', name)):
            metrics.append(element['id'])
    return TabbedTypingContext(snapshot, target, passive_metrics=metrics)
