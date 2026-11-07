from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_windows_adapter import NativeWindowsAdapter
from native_action_control import NativeActionControl
from native_typing_context import TabbedTypingContext


def setup(grants=None):
    state = {'window': {'hwnd': 1, 'pid': 2, 'created': 3}, 'foreground': True,
             'available': True, 'truncated': False, 'geometry': [0, 0, 300, 200],
             'elements': [{'id': 'edit', 'rect': [10, 10, 200, 50], 'enabled': True,
                           'visible': True, 'focused': True, 'password': False, 'value': ''}]}
    observer = Mock(); observer.read.side_effect = lambda: deepcopy(state)
    observer.hit_test.return_value = 'edit'
    transport = Mock()
    def write(text, *, preflight, cancelled):
        for char in text:
            preflight()
            state['elements'][0]['value'] += char
    transport.type_text.side_effect = write
    transport.click.side_effect = lambda *args, preflight, cancelled: preflight()
    transport.key_tap.side_effect = lambda *args, preflight, cancelled: preflight()
    grants = {'edit': {'actions': ['type', 'click', 'key'], 'keys': ['Tab']}} if grants is None else grants
    adapter = NativeWindowsAdapter(observer, transport, grants, lambda: None)
    return adapter, observer, transport, state


def test_typing_allows_own_value_change_and_checks_each_batch():
    a, o, t, s = setup(); control = NativeActionControl(a, s['window'], lambda: None)
    result = control.act({'op': 'type', 'target': 'edit', 'text': 'abc'}, control.observe(),
                          lambda action, before, after: after['elements'][0]['value'] == 'abc')
    assert result['status'] == 'verified'
    assert o.read.call_count == 6


def tabbed_setup():
    a,o,t,s = setup()
    edit = s['elements'][0]
    edit.update(parent_id='root', type='ControlType.Document', name='editor')
    root = dict(edit, id='root', parent_id=None, type='ControlType.Window', name='Untitled')
    tab = dict(root, id='tab', parent_id='root', type='ControlType.TabItem', selected=True)
    label = dict(root, id='label', parent_id='tab', type='ControlType.Text')
    other = dict(label, id='other', parent_id='root', name='unchanged')
    s['elements'].extend([root,tab,label,other])
    a.typing_context = TabbedTypingContext(s, 'edit')
    return a,o,t,s


def test_tabbed_typing_accepts_caption_and_tab_presentation_changes():
    a,o,t,s = tabbed_setup()
    def write(text, *, preflight, cancelled):
        for char in text:
            preflight()
            s['elements'][0]['value'] += char
            s['elements'][1]['name'] = '*' + s['elements'][0]['value']
            s['elements'][2]['name'] = s['elements'][0]['value']
            s['elements'][3]['name'] = s['elements'][0]['value']
        # Tabs may replace their close button with a modified-document icon.
        s['elements'].pop(3)
    t.type_text.side_effect = write
    control = NativeActionControl(a,s['window'],lambda:None)
    result = control.act({'op':'type','target':'edit','text':'abc'},control.observe(),
        lambda act,before,after:after['elements'][0]['value']=='abc')
    assert result['verified'] is True


@pytest.mark.parametrize('change',['tab_selection','tab_identity','target_geometry','other_label','target_value'])
def test_tabbed_typing_refuses_document_or_unrelated_changes(change):
    a,o,t,s = tabbed_setup()
    expected = a.read()
    def write(text, *, preflight, cancelled):
        preflight()
        s['elements'][0]['value'] = 'a'
        if change == 'tab_selection':s['elements'][2]['selected'] = False
        if change == 'tab_identity':s['elements'][2]['id'] = 'new-document'
        if change == 'target_geometry':s['elements'][0]['rect'] = [20,10,200,50]
        if change == 'other_label':s['elements'][4]['name'] = 'changed'
        if change == 'target_value':s['elements'][0]['value'] = 'external'
        preflight()
        pytest.fail('second character must not be sent')
    t.type_text.side_effect = write
    with pytest.raises(RuntimeError):
        a.dispatch({'op':'type','target':'edit','text':'abc'},expected=expected,cancelled=lambda:False)


def test_caption_change_before_first_character_is_not_exempt():
    a,o,t,s = tabbed_setup()
    expected = a.read()
    s['elements'][1]['name'] = 'another document'
    with pytest.raises(RuntimeError):
        a.dispatch({'op':'type','target':'edit','text':'abc'},expected=expected,cancelled=lambda:False)
    assert s['elements'][0]['value'] == ''


def test_document_anchor_is_checked_before_first_character_even_after_new_observation():
    a,o,t,s = tabbed_setup()
    s['elements'][2]['id'] = 'other_document'
    with pytest.raises(RuntimeError, match='active_document_changed'):
        a.dispatch({'op':'type','target':'edit','text':'abc'},expected=a.read(),cancelled=lambda:False)
    assert s['elements'][0]['value'] == ''


def test_only_explicit_passive_metrics_can_change_during_typing():
    a,o,t,s = tabbed_setup()
    pane = dict(s['elements'][1],id='status',parent_id='root',type='ControlType.Pane',enabled=False)
    metric = dict(s['elements'][3],id='metric',parent_id='status',editable=False,password=False,
                  name='0 caractere',value='0 caractere',rect=[10,10,200,50])
    s['elements'].extend([pane,metric])
    a.typing_context = TabbedTypingContext(s,'edit',passive_metrics=['metric'])
    expected = a.read()
    def write(text, *, preflight, cancelled):
        preflight()
        s['elements'][0]['value'] = 'a'
        metric.update(name='1 caractere',value='1 caractere',rect=[10,10,99,50])
        preflight()
        # Even an approved metric cannot become an editable/focused field.
        s['elements'][0]['value'] = 'ab'
        metric['editable'] = True
        with pytest.raises(RuntimeError, match='target_changed'):preflight()
    t.type_text.side_effect = write
    a.dispatch({'op':'type','target':'edit','text':'abc'},expected=expected,cancelled=lambda:False)


@pytest.mark.parametrize('change', ['focus', 'geometry', 'window', 'password', 'value'])
def test_changes_between_controller_and_dispatch_refuse(change):
    a, o, t, s = setup(); expected = a.read()
    if change == 'focus': s['foreground'] = False
    if change == 'geometry': s['geometry'][0] = 100
    if change == 'window': s['window']['created'] = 4
    if change == 'password': s['elements'][0]['password'] = True
    if change == 'value': s['elements'][0]['value'] = 'user'
    with pytest.raises((RuntimeError, ValueError)):
        a.dispatch({'op': 'type', 'target': 'edit', 'text': 'abc'}, expected=expected, cancelled=lambda: False)
    assert s['elements'][0]['value'] in ('', 'user')


def test_ungranted_controls_are_read_only():
    a, o, t, s = setup({})
    assert a.read()['elements'][0]['actions'] == []
    with pytest.raises(ValueError):
        a.dispatch({'op': 'click', 'target': 'edit'}, expected=a.read(), cancelled=lambda: False)
    t.click.assert_not_called()


def test_obstructed_click_has_no_success():
    a, o, t, s = setup(); o.hit_test.return_value = 'popup'
    with pytest.raises(RuntimeError, match='obstructed'):
        a.dispatch({'op': 'click', 'target': 'edit'}, expected=a.read(), cancelled=lambda: False)


def test_click_on_observed_label_child_is_click_on_authorized_parent():
    a, o, t, s = setup()
    child = deepcopy(s['elements'][0]); child.update(id='label', parent_id='edit')
    s['elements'].append(child)
    o.hit_test.return_value = 'label'
    a.dispatch({'op': 'click', 'target': 'edit'}, expected=a.read(), cancelled=lambda: False)
    t.click.assert_called_once()


@pytest.mark.parametrize('fault', ['truncated', 'duplicate', 'invalid_rect'])
def test_invalid_observation(fault):
    a, o, t, s = setup()
    if fault == 'truncated': s['truncated'] = True
    if fault == 'duplicate': s['elements'] *= 2
    if fault == 'invalid_rect': s['geometry'][0] = float('nan')
    with pytest.raises(ValueError): a.read()


def test_no_grants_for_global_shortcut():
    with pytest.raises(ValueError): setup({'edit': {'actions': ['key'], 'keys': ['Win+R']}})


def test_cancellation_during_guard_prevents_input():
    a, o, t, s = setup(); expected = a.read()
    a.guard = a.cancel
    with pytest.raises(RuntimeError, match='cancelled'):
        a.dispatch({'op': 'type', 'target': 'edit', 'text': 'abc'}, expected=expected, cancelled=lambda: False)
    assert s['elements'][0]['value'] == ''


def test_only_target_ancestor_aggregate_text_may_change():
    a, o, t, s = setup()
    s['elements'][0]['parent_id'] = 'document'
    parent = deepcopy(s['elements'][0]); parent.update(id='document', parent_id=None, focused=False)
    sibling = deepcopy(parent); sibling.update(id='other', value='unchanged')
    s['elements'].extend([parent, sibling])
    expected = a.read()
    def input_with_aggregate(text, *, preflight, cancelled):
        preflight()
        s['elements'][0]['value'] = 'a'
        parent['value'] = 'a'
        preflight()
        sibling['value'] = 'external change'
        s['elements'][0]['value'] = 'ab'
        parent['value'] = 'ab'
        with pytest.raises(RuntimeError, match='changed'):
            preflight()
    t.type_text.side_effect = input_with_aggregate
    a.dispatch({'op': 'type', 'target': 'edit', 'text': 'ab'}, expected=expected, cancelled=lambda: False)


def test_external_edit_in_target_is_not_ignored_during_typing():
    a,o,t,s=setup(); expected=a.read()
    def interfering_transport(text,*,preflight,cancelled):
        preflight()
        s['elements'][0]['value']='external'
        preflight()
    t.type_text.side_effect=interfering_transport
    with pytest.raises(RuntimeError,match='text_changed'):
        a.dispatch({'op':'type','target':'edit','text':'abc'},expected=expected,cancelled=lambda:False)
