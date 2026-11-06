"""Isolated real DOM observation/actions. No desktop input, network or user profile.

The caller must establish its FPS/RAM guard before start. Observations expose
visible controls only; actions use exact scoped ids, never arbitrary selectors.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]

HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; form-action 'none'; connect-src 'none'">
<style>body{font:18px Arial;padding:25px}label{display:block;margin:15px}button{margin:8px} [hidden]{display:none!important}</style>
</head><body data-scope="SCOPE" data-revision="0" data-page="home">
<h1>Application de demonstration Alice</h1>
<nav><button id="nav_home" data-label="Accueil">Accueil</button><button id="nav_form" data-label="Formulaire">Formulaire</button></nav>
<section id="home"><p>Documents fictifs. Aucune donnee personnelle.</p>
<button id="help_a" data-label="Aide">Aide</button><button id="help_b" data-label="Aide">Aide</button></section>
<section id="form" hidden>
<label>Titre <input id="title" data-label="Titre" maxlength="80"></label>
<label>Categorie <select id="category" data-label="Categorie"><option value="personnel">Personnel</option><option value="travail">Travail</option><option value="loisir">Loisir</option></select></label>
<label><input id="reminder" data-label="Rappel" type="checkbox">Rappel</label>
<button id="save" data-label="Enregistrer">Enregistrer</button>
<button id="send" data-label="Envoyer" disabled>Envoyer</button></section>
<button id="undo" data-label="Annuler la derniere modification" disabled>Annuler la derniere modification</button>
<p id="status" role="status">Pret</p><pre id="saved">Aucun document enregistre</pre>
<script>
(() => {
 const el=id=>document.getElementById(id), body=document.body;
 let history=[], saved=null;
 const current=()=>({page:body.dataset.page,title:el('title').value,category:el('category').value,reminder:el('reminder').checked,saved:saved});
 let previous=current();
 function paint(){el('home').hidden=body.dataset.page!=='home';el('form').hidden=body.dataset.page!=='form';el('undo').disabled=!history.length;el('saved').textContent=saved?JSON.stringify(saved):'Aucun document enregistre';}
 function changed(message){history.push(previous);body.dataset.revision=String(Number(body.dataset.revision)+1);el('status').textContent=message;paint();previous=current();}
 for(const id of ['nav_home','nav_form'])el(id).onclick=()=>{body.dataset.page=id==='nav_home'?'home':'form';changed('Page ouverte');};
 el('title').oninput=()=>changed('Titre modifie');
 el('category').onchange=()=>changed('Categorie modifiee');
 el('reminder').onchange=()=>changed('Rappel modifie');
 el('save').onclick=()=>{saved={title:el('title').value,category:el('category').value,reminder:el('reminder').checked};changed('Document enregistre');};
 for(const id of ['help_a','help_b'])el(id).onclick=()=>changed('Aide ouverte');
 el('undo').onclick=()=>{if(!history.length)return;let state=history.pop();body.dataset.page=state.page;el('title').value=state.title;el('category').value=state.category;el('reminder').checked=state.reminder;saved=state.saved;body.dataset.revision=String(Number(body.dataset.revision)+1);el('status').textContent='Modification annulee';paint();previous=current();};
 paint();
})();
</script></body></html>'''

OBSERVE = r'''() => {
 const visible=e=>!!(e.getClientRects().length)&&getComputedStyle(e).visibility!=='hidden';
 return {scope:document.body.dataset.scope,revision:Number(document.body.dataset.revision),page:document.body.dataset.page,
 elements:[...document.querySelectorAll('button,input,select')].filter(visible).map(e=>({
 id:e.id,role:e.tagName==='BUTTON'?'button':e.tagName==='SELECT'?'combobox':e.type==='checkbox'?'checkbox':'textbox',
 label:e.dataset.label,enabled:!e.disabled,value:e.type==='checkbox'?e.checked:e.tagName==='BUTTON'?null:e.value,
 options:e.tagName==='SELECT'?[...e.options].map(o=>({value:o.value,label:o.textContent})):[]})),
 status:document.getElementById('status').textContent,saved:(()=>{let t=document.getElementById('saved').textContent;return t==='Aucun document enregistre'?null:JSON.parse(t);})()};
}'''


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_action(action, observation):
    """Strict capability contract, independent of browser APIs."""
    if not isinstance(action, dict) or set(action) - {'op', 'target', 'value'}:
        raise ValueError('action_schema')
    op, target = action.get('op'), action.get('target')
    if op not in {'click', 'fill', 'select', 'check'} or not isinstance(target, str):
        raise ValueError('action_schema')
    if target not in {'nav_home', 'nav_form', 'title', 'category', 'reminder', 'save', 'send', 'help_a', 'help_b', 'undo'}:
        raise ValueError('target_outside_scope')
    if set(action) != ({'op', 'target'} if op == 'click' else {'op', 'target', 'value'}):
        raise ValueError('action_schema')
    found = [e for e in observation['elements'] if e['id'] == target]
    if len(found) != 1:
        raise ValueError('target_missing_or_ambiguous')
    element = found[0]
    if not element['enabled']:
        raise ValueError('target_disabled')
    required = {'click': 'button', 'fill': 'textbox', 'select': 'combobox', 'check': 'checkbox'}
    if element['role'] != required[op]:
        raise ValueError('operation_role_mismatch')
    value = action.get('value')
    if op == 'fill' and (not isinstance(value, str) or len(value) > 80 or any(ord(c) < 32 for c in value)):
        raise ValueError('invalid_text')
    if op == 'select' and value not in [o['value'] for o in element['options']]:
        raise ValueError('invalid_option')
    if op == 'check' and type(value) is not bool:
        raise ValueError('invalid_boolean')
    return element


class BrowserDemo:
    def __init__(self, guard, *, max_age=10.0, clock=time.monotonic):
        if not callable(guard):
            raise TypeError('An active FPS/RAM guard callback is required')
        self.guard, self.max_age, self.clock = guard, max_age, clock
        self.scope = 'validation_browser_' + secrets.token_hex(12)
        self._issued = None
        self._history = []
        self._owner = []
        self._lock = threading.Lock()
        self._stopping = False
        self._closed_once = False
        self._playwright = self.browser = self.context = self.page = None
        self.closed = False

    def _browser_args(self):
        return ['--disable-gpu', '--disable-background-networking', '--disable-extensions', '--mute-audio']

    def start(self):
        if self.closed or self.page:
            raise RuntimeError('Demo cannot be restarted')
        self.guard()
        from playwright.sync_api import sync_playwright
        previous_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'runtime/playwright')
        before = {(p.pid, p.create_time()) for p in psutil.Process().children(recursive=True)}
        try:
            self._playwright = sync_playwright().start()
            # Register the owned driver before browser launch; the FPS watchdog
            # can terminate its descendants even while launch is still pending.
            drivers = []
            for process in psutil.Process().children(recursive=True):
                identity = (process.pid, process.create_time())
                if identity not in before and process.name().lower() in ('node.exe', 'node'):
                    command = ' '.join(process.cmdline()).replace('\\', '/').lower()
                    if '/playwright/driver/' in command:
                        drivers.append(identity)
            if len(drivers) != 1:
                raise RuntimeError('Cannot identify the owned Playwright driver')
            with self._lock:
                self._owner = drivers
                stopping = self._stopping
            if stopping:
                self.stop_owned()
                raise RuntimeError('Guard stopped browser startup')
            self.guard()
            self.browser = self._playwright.chromium.launch(headless=True, args=self._browser_args())
            self._record_descendants()
            self.guard()
            self.context = self.browser.new_context(viewport={'width': 900, 'height': 600}, service_workers='block', accept_downloads=False)
            self.context.route('**/*', lambda route: route.abort())
            self.page = self.context.new_page()
            self.page.set_default_timeout(2000)
            self.page.set_content(HTML.replace('SCOPE', self.scope), wait_until='load')
            self.guard()
            return self
        except BaseException:
            self.close()
            raise
        finally:
            if previous_path is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = previous_path

    def _read(self):
        if self.closed or not self.page:
            raise RuntimeError('Demo is not running')
        value = self.page.evaluate(OBSERVE)
        if value['scope'] != self.scope or self.page.url != 'about:blank':
            raise RuntimeError('Document scope changed')
        return value

    def observe(self):
        self.guard()
        value = self._read()
        value['observed_at'] = self.clock()
        self._issued = (fingerprint(value), copy.deepcopy(value))
        return value

    def act(self, action, snapshot):
        self.guard()
        before = self._read()
        try:
            if not self._issued or fingerprint(snapshot) != self._issued[0]:
                raise ValueError('unknown_or_modified_observation')
            age = self.clock() - snapshot['observed_at']
            if age < 0 or age > self.max_age:
                raise ValueError('observation_expired')
            observed = {k: v for k, v in snapshot.items() if k != 'observed_at'}
            if before != observed:
                raise ValueError('observation_changed')
            element = validate_action(action, before)
        except (ValueError, TypeError, KeyError) as error:
            return {'ok': False, 'verified': False, 'reason': str(error), 'after': self.observe()}
        self._issued = None  # a capability is single-use even if the action fails
        target, op = action['target'], action['op']
        # IDs come from our own issued DOM and are restricted, not CSS selectors supplied by the model.
        locator = self.page.locator(f'[id="{target}"]')
        self.guard()
        try:
            if op == 'click': locator.click()
            elif op == 'fill': locator.fill(action['value'])
            elif op == 'select': locator.select_option(action['value'])
            else: locator.set_checked(action['value'])
            self.guard()
            after = self.observe()
            expected_undo = self._history[-1] if self._history else None
            verified = self._verify(action, before, after, expected_undo)
            if verified and after['revision'] > before['revision']:
                if target == 'undo': self._history.pop()
                else: self._history.append(copy.deepcopy(before))
            return {'ok': verified, 'verified': verified, 'reason': 'verified' if verified else 'postcondition_failed', 'after': after}
        except Exception as error:
            self._issued = None
            raise RuntimeError('Action interrupted; do not retry without a new observation') from error

    @staticmethod
    def _verify(action, before, after, expected_undo=None):
        op, target = action['op'], action['target']
        if after['scope'] != before['scope']:
            return False
        if op != 'click':
            values = [e['value'] for e in after['elements'] if e['id'] == target]
            return values == [action['value']]
        if after['revision'] <= before['revision']:
            return False
        if target in ('nav_home', 'nav_form'):
            return after['page'] == ('home' if target == 'nav_home' else 'form')
        if target == 'save':
            values = {e['id']: e['value'] for e in before['elements']}
            return after['saved'] == {k: values[k] for k in ('title', 'category', 'reminder')}
        if target == 'undo':
            if expected_undo is None:
                return False
            def state(snapshot):
                return {key: snapshot[key] for key in ('page', 'saved')}, [
                    e for e in snapshot['elements'] if e['id'] != 'undo']
            return after['status'] == 'Modification annulee' and state(after) == state(expected_undo)
        return after['status'] == 'Aide ouverte'

    def screenshot(self):
        """Only this isolated page; never the desktop."""
        self.guard()
        self._read()
        return self.page.screenshot(type='png')

    def stop_owned(self):
        """Thread-safe emergency stop; never uses Playwright across threads."""
        with self._lock:
            self._stopping = True
            identities = list(self._owner)
        owned = []
        for pid, created in identities:
            try:
                process = psutil.Process(pid)
                if process.create_time() == created:
                    owned.extend(process.children(recursive=True))
                    owned.append(process)
            except psutil.Error:
                pass
        with self._lock:
            for process in owned:
                try:
                    identity = (process.pid, process.create_time())
                    if identity not in self._owner:
                        self._owner.append(identity)
                except psutil.Error:
                    pass
        for process in reversed(owned):
            try: process.kill()
            except psutil.Error: pass
        psutil.wait_procs(owned, timeout=3)

    def _record_descendants(self):
        with self._lock:
            identities = list(self._owner)
        descendants = []
        for pid, created in identities:
            try:
                process = psutil.Process(pid)
                if process.create_time() == created:
                    descendants += [(p.pid, p.create_time()) for p in process.children(recursive=True)]
            except psutil.Error:
                pass
        with self._lock:
            self._owner = list(set(self._owner + descendants))

    @property
    def owned_stopped(self):
        with self._lock:
            identities = list(self._owner)
        for pid, created in identities:
            try:
                if psutil.Process(pid).create_time() == created:
                    return False
            except psutil.NoSuchProcess:
                pass
            except psutil.Error:
                return False
        return True

    def close(self):
        if self._closed_once:
            self.stop_owned()
            return
        self._closed_once = True
        self.closed = True
        self._record_descendants()
        failure = None
        try:
            if self.browser:
                self.browser.close()
        except Exception as error:
            failure = error
        finally:
            try:
                if self._playwright:
                    self._playwright.stop()
            except Exception as error:
                failure = failure or error
            finally:
                self.stop_owned()
        # A FPS guard may already have killed the driver. Cleanup succeeds only
        # when the actual owned-process postcondition holds, not from a closed pipe.
        if failure and not self.owned_stopped:
            raise failure

