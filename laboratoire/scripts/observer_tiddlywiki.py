"""Scoped DOM adapter for an unmodified, local TiddlyWiki application.

All wiki files are temporary validation data. The model cannot choose URLs,
selectors, paths or JavaScript. Actual note writes use UI events only.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import quote, urlsplit
import requests

from observer_browser import BrowserDemo, fingerprint, ROOT

PACKAGE = ROOT / 'runtime/tiddlywiki/node_modules/tiddlywiki'
NEW = 'button[title="Create a new tiddler"]'
TITLE = '.tc-tiddler-edit-frame input.tc-titlebar'
BODY = '.tc-tiddler-edit-frame iframe.tc-edit-texteditor-body'
SAVE = '.tc-tiddler-edit-frame button[aria-label="Confirm changes to this tiddler"]'
CANCEL = '.tc-tiddler-edit-frame button[aria-label="Discard changes to this tiddler"]'

def parse_tid(text):
    head, separator, body = text.partition('\n\n')
    if not separator:
        return None
    fields = dict(line.split(': ', 1) for line in head.splitlines() if ': ' in line)
    if 'title' not in fields or 'draft.of' in fields:
        return None
    return {'title': fields['title'], 'body': body}

def validate_note_action(action, snapshot):
    if not isinstance(action, dict):
        raise ValueError('action_schema')
    if action.get('op') == 'fill':
        if set(action) != {'op', 'target', 'value'} or action['target'] not in ('title', 'body'):
            raise ValueError('action_schema')
        value = action['value']
        if not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
            raise ValueError('invalid_text')
        if action['target'] == 'title' and (not value or '\n' in value or '\r' in value or value.startswith('$:/')):
            raise ValueError('invalid_title')
    elif action not in ({'op': 'click', 'target': 'save'}, {'op': 'click', 'target': 'cancel'}):
        raise ValueError('action_schema')
    found = [e for e in snapshot['elements'] if e['id'] == action['target']]
    if len(found) != 1 or not found[0]['enabled']:
        raise ValueError('target_missing_ambiguous_or_disabled')

class TiddlyWikiApp(BrowserDemo):
    def __init__(self, guard, **kwargs):
        super().__init__(guard, **kwargs)
        self._server = None
        self._init = None
        self._wiki_temp = None
        self._server_log = None
        self._saved = None
        self.origin = None
        self._last_title = None
        self._editing_original = None
        self.diagnostics = {}
        self._http = requests.Session()
        self._http.trust_env = False

    def start(self):
        self.guard()
        node = shutil.which('node')
        manifest = json.loads((PACKAGE / 'package.json').read_text(encoding='utf-8'))
        if manifest['version'] != '5.4.1' or not node:
            raise RuntimeError('Expected local TiddlyWiki5.4.1 and Node')
        base = ROOT / 'data/validation'
        base.mkdir(parents=True, exist_ok=True)
        self._wiki_temp = tempfile.TemporaryDirectory(prefix='validation_tiddlywiki_', dir=base)
        self.wiki = Path(self._wiki_temp.name)/'wiki'
        self._server_log = (Path(self._wiki_temp.name)/'server.log').open('w', encoding='utf-8')
        command = [node, str(PACKAGE/'tiddlywiki.js'), str(self.wiki)]
        flags = subprocess.CREATE_NO_WINDOW
        try:
            self.guard()
            self._init = subprocess.Popen(command+['--init', 'server'], cwd=ROOT,
                stdout=self._server_log, stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic()+20
            while self._init.poll() is None:
                self.guard()
                if time.monotonic()>deadline: raise RuntimeError('Wiki initialization timeout')
                time.sleep(.05)
            if self._init.returncode:
                raise RuntimeError('Wiki initialization failed')
            password = secrets.token_hex(24)
            (self.wiki/'credentials.csv').write_text('username,password\nvalidation,'+password+'\n', encoding='utf-8')
            self._http.auth = ('validation', password)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            self.origin = f'http://127.0.0.1:{port}'
            self.guard()
            self._server = subprocess.Popen(command+['--listen', 'host=127.0.0.1', f'port={port}',
                'credentials=credentials.csv', 'readers=validation', 'writers=validation'], cwd=ROOT,
                stdout=self._server_log, stderr=subprocess.STDOUT, creationflags=flags)
            deadline=time.monotonic()+30
            while True:
                self.guard()
                if self._server.poll() is not None: raise RuntimeError('Wiki server exited')
                try:
                    response=self._http.get(self.origin+'/status',timeout=.5)
                    if response.status_code==200: break
                except requests.RequestException:
                    pass
                if time.monotonic()>deadline: raise RuntimeError('Wiki server timeout')
                time.sleep(.1)
            super().start()
            self.context.unroute('**/*')
            self.context.set_extra_http_headers({'Authorization': requests.auth._basic_auth_str('validation',password)})
            self.context.route('**/*', lambda route: route.continue_() if
                urlsplit(route.request.url).scheme+'://'+urlsplit(route.request.url).netloc==self.origin else route.abort())
            self.page.goto(self.origin, wait_until='load', timeout=15000)
            self._diagnose()
            self.page.locator(NEW).wait_for(state='visible',timeout=15000)
            self.guard()
            return self
        except BaseException:
            self._diagnose()
            self.close()
            raise

    def _diagnose(self):
        """Bounded fictitious UI evidence only; no credentials, URL or page source."""
        if self.page and not self.closed:
            try:
                self.diagnostics = self.page.evaluate('''() => ({
                    title:document.title, body:document.body.innerText.slice(0,1200),
                    buttons:[...document.querySelectorAll('button')].slice(0,35).map(e=>({
                        title:e.title,aria:e.getAttribute('aria-label'),text:e.innerText.slice(0,80)}))})''')
            except Exception:
                pass

    def prepare_new(self):
        self.guard()
        if self.page.locator(TITLE).count():
            raise RuntimeError('An editor is already open')
        self.page.locator(NEW).click()
        self.page.locator(TITLE).wait_for(state='visible')
        self.page.locator(BODY).wait_for(state='visible')
        self._saved = None
        self._editing_original = None
        return self.observe()

    def _body(self):
        count=self.page.locator(BODY).count()
        if count>1: raise RuntimeError('Ambiguous body editor')
        if not count: return self.page.locator('[data-validation-missing-editor]')
        return self.page.frame_locator(BODY).locator('textarea')

    def _read(self):
        if self.closed or not self.page or urlsplit(self.page.url).scheme+'://'+urlsplit(self.page.url).netloc != self.origin:
            raise RuntimeError('Wiki scope changed')
        elements=[]
        for field,selector,label,role in [('title',TITLE,'Titre','textbox'),('body',BODY,'Texte','textbox'),('save',SAVE,'Enregistrer','button')]:
            locator=self._body() if field=='body' else self.page.locator(selector)
            for i in range(locator.count()):
                element=locator.nth(i)
                if element.is_visible():
                    elements.append({'id':field,'role':role,'label':label,'enabled':element.is_enabled(),
                        'value':element.input_value() if role=='textbox' else None,'options':[]})
        cancel=self.page.locator(CANCEL)
        for i in range(cancel.count()):
            if cancel.nth(i).is_visible():
                elements.append({'id':'cancel','role':'button','label':'Annuler les modifications',
                                 'enabled':cancel.nth(i).is_enabled(),'value':None,'options':[]})
        values={'elements':elements,'saved':copy.deepcopy(self._saved)}
        return {'scope':self.scope,'revision':fingerprint(values),'page':'editor' if elements else 'notes',
                **values,'status':'Application TiddlyWiki locale'}

    def _disk_note(self, title):
        for path in (self.wiki/'tiddlers').rglob('*.tid'):
            parsed=parse_tid(path.read_text(encoding='utf-8'))
            if parsed and parsed['title']==title:
                return parsed
        return None

    def act(self, action, snapshot):
        self.guard()
        before=self._read()
        try:
            if not self._issued or fingerprint(snapshot)!=self._issued[0]:
                raise ValueError('unknown_or_modified_observation')
            age=self.clock()-snapshot['observed_at']
            if age<0 or age>self.max_age: raise ValueError('observation_expired')
            if before!={k:v for k,v in snapshot.items() if k!='observed_at'}:
                raise ValueError('observation_changed')
            validate_note_action(action,before)
        except (ValueError,KeyError,TypeError) as error:
            return {'ok':False,'verified':False,'reason':str(error),'after':self.observe()}
        self._issued=None
        self.guard()
        if action['op']=='fill':
            locator=self.page.locator(TITLE) if action['target']=='title' else self._body()
            locator.fill(action['value'])
            after=self.observe()
            verified=any(e['id']==action['target'] and e['value']==action['value'] for e in after['elements'])
        elif action['target']=='cancel':
            expected=copy.deepcopy(self._editing_original)
            def discard_dialog(dialog):
                if dialog.type=='confirm' and 'discard' in dialog.message.lower():dialog.accept()
                else:dialog.dismiss()
            self.page.once('dialog',discard_dialog)
            try:
                self.page.locator(CANCEL).click(timeout=5000)
                self.page.locator(TITLE).wait_for(state='detached',timeout=5000)
            finally:
                self.page.remove_listener('dialog',discard_dialog)
            self._saved=expected
            after=self.observe()
            verified=(not after['elements'] and
                      (expected is None or self._disk_note(expected['title'])==expected))
        else:
            fields={e['id']:e['value'] for e in before['elements']}
            target={'title':fields['title'],'body':fields['body']}
            self._last_title=target['title']
            self.page.locator(SAVE).click()
            self.page.locator(TITLE).wait_for(state='detached',timeout=5000)
            deadline=time.monotonic()+10
            while True:
                self.guard()
                persisted=self._disk_note(target['title'])
                # Existing notes may still contain the previous version during sync.
                # Presence alone is not proof the requested update was persisted.
                if persisted == target: break
                if time.monotonic()>deadline: raise RuntimeError('Note was not persisted')
                time.sleep(.1)
            self._saved=persisted
            after=self.observe()
            verified=persisted==target
        return {'ok':verified,'verified':verified,'reason':'verified' if verified else 'postcondition_failed','after':after}

    def verify_persisted(self, expected):
        self.guard()
        disk=self._disk_note(expected['title'])
        self.page.goto(self.origin+'/#'+quote(expected['title'],safe=''),wait_until='load')
        # Repeated verification of the same URL must really reload persisted data.
        self.page.reload(wait_until='load')
        title_selector=json.dumps(expected['title'],ensure_ascii=False)
        frame=self.page.locator(f'.tc-tiddler-view-frame[data-tiddler-title={title_selector}]')
        frame.get_by_role('button',name='Edit this tiddler',exact=True).click(timeout=5000)
        self.page.locator(TITLE).wait_for(state='visible')
        actual={'title':self.page.locator(TITLE).input_value(),'body':self._body().input_value()}
        self._editing_original=copy.deepcopy(actual)
        self.persistence_evidence={'disk':disk,'reopened':actual}
        return disk==expected and actual==expected

    def tamper_field_for_test(self, field, value):
        self.guard()
        if field not in ('title','body') or not isinstance(value,str):
            raise ValueError('Invalid fault injection')
        locator=self.page.locator(TITLE) if field=='title' else self._body()
        locator.fill(value)

    def stop_owned(self):
        for process in (self._server,self._init):
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=3)
        super().stop_owned()

    @property
    def owned_stopped(self):
        return super().owned_stopped and all(p is None or p.poll() is not None for p in (self._server,self._init))

    def close(self):
        try:
            super().close()
        finally:
            self._http.close()
            if self._server_log and not self._server_log.closed: self._server_log.close()
            if self._wiki_temp:
                target=Path(self._wiki_temp.name).resolve()
                base=(ROOT/'data/validation').resolve()
                if target.parent!=base or not target.name.startswith('validation_tiddlywiki_'):
                    raise RuntimeError('Refusing cleanup outside validation root')
                self._wiki_temp.cleanup()
