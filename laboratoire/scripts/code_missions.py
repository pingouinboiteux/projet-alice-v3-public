"""Persistent local code missions. Only the isolated atelier runner can execute."""
import json
from pathlib import Path
import secrets
import sqlite3
from datetime import datetime, timezone

from codex_link import ATELIER, ROOT, run_task

DATA = ROOT / 'data/runtime/code_missions.sqlite3'
WORKSPACES = ATELIER / 'missions'
STATES = {'ready', 'running', 'executed', 'failed', 'cancelled', 'interrupted', 'applied', 'restored'}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class MissionStore:
    def __init__(self, database=DATA, workspaces=WORKSPACES):
        self.database = Path(database)
        self.workspaces = Path(workspaces)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.workspaces.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY, prompt TEXT NOT NULL, workspace TEXT NOT NULL,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL, updated TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
                source TEXT, source_sha TEXT)''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(missions)')}
            if 'source' not in columns:
                db.execute('ALTER TABLE missions ADD COLUMN source TEXT')
            if 'source_sha' not in columns:
                db.execute('ALTER TABLE missions ADD COLUMN source_sha TEXT')
            db.execute("UPDATE missions SET state='interrupted', updated=? WHERE state='running'", (_now(),))

    def _connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, prompt, *, source=None, source_sha=None, source_bytes=None):
        if type(prompt) is not str or not 1 <= len(prompt.strip()) <= 4000:
            raise ValueError('Demande de code vide ou trop longue.')
        identity = secrets.token_hex(6)
        folder = self.workspaces / identity
        folder.mkdir(exist_ok=False)
        if source is not None:
            staged = folder / source
            staged.parent.mkdir(parents=True)
            staged.write_bytes(source_bytes)
        now = _now()
        with self._connect() as db:
            db.execute('''INSERT INTO missions(id,prompt,workspace,state,created,updated,source,source_sha)
                VALUES (?,?,?,?,?,?,?,?)''',
                (identity, prompt.strip(), str(folder), 'ready', now, now, source, source_sha))
        return self.get(identity)

    def get(self, identity):
        if type(identity) is not str or len(identity) != 12 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Identifiant de mission invalide.')
        with self._connect() as db:
            row = db.execute('SELECT * FROM missions WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('Mission introuvable.')
        result = dict(row)
        result['result'] = json.loads(result['result'])
        return result

    def list(self, limit=8):
        with self._connect() as db:
            rows = db.execute('SELECT id,state,attempts,updated,substr(prompt,1,80) AS goal FROM missions ORDER BY created DESC LIMIT ?',
                              (limit,)).fetchall()
        return [dict(row) for row in rows]

    def start(self, identity):
        mission = self.get(identity)
        if mission['state'] not in {'ready', 'failed', 'interrupted', 'cancelled'}:
            raise ValueError('Cette mission ne peut pas etre relancee.')
        with self._connect() as db:
            changed = db.execute('''UPDATE missions SET state='running', attempts=attempts+1,
                updated=? WHERE id=? AND state=?''', (_now(), identity, mission['state']))
            if changed.rowcount != 1:
                raise ValueError('Etat de mission modifie entretemps.')
        return self.get(identity)

    def finish(self, identity, result):
        state = {'completed':'executed', 'cancelled':'cancelled'}.get(result['status'], 'failed')
        safe = {'changed_files':result.get('changed_files', []),
                'message':result.get('message', '')[:1500],
                'seconds':result.get('seconds', 0),
                'runner_status':result['status']}
        with self._connect() as db:
            changed = db.execute('UPDATE missions SET state=?, result=?, updated=? WHERE id=? AND state=?',
                                 (state, json.dumps(safe, ensure_ascii=False), _now(), identity, 'running'))
            if changed.rowcount != 1:
                raise ValueError('Etat de mission modifie entretemps.')
        return self.get(identity)

    def mark_applied(self, identity):
        with self._connect() as db:
            changed = db.execute("UPDATE missions SET state='applied',updated=? WHERE id=? AND state='executed'",
                                 (_now(), identity))
            if changed.rowcount != 1:
                raise ValueError('Mission non prete a appliquer.')
        return self.get(identity)

    def mark_restored(self, identity):
        with self._connect() as db:
            changed = db.execute("UPDATE missions SET state='restored',updated=? WHERE id=? AND state='applied'",
                                 (_now(), identity))
            if changed.rowcount != 1:
                raise ValueError('Mission non prete a restaurer.')
        return self.get(identity)


def command(text):
    stripped = text.strip()
    if stripped == '/missions':
        return ('list', None)
    if stripped.startswith('/mission '):
        return ('show', stripped.split(' ', 1)[1].strip())
    if stripped.startswith('/reprendre '):
        return ('resume', stripped.split(' ', 1)[1].strip())
    if stripped.startswith('/appliquer '):
        return ('apply', stripped.split(' ', 1)[1].strip())
    if stripped.startswith('/restaurer-code '):
        return ('restore', stripped.split(' ', 1)[1].strip())
    if stripped.startswith('/faire fichier '):
        details = stripped[len('/faire fichier '):]
        if ' : ' not in details:
            raise ValueError('Utilise /faire fichier scripts/nom.py : ta demande.')
        source, prompt = details.split(' : ', 1)
        return ('new_file', (source.strip(), prompt.strip()))
    if stripped.lower().startswith(("dans l'atelier ", 'dans l’atelier ')):
        return ('new', stripped.split(' ', 2)[2].strip())
    if stripped.startswith('/faire '):
        return ('new', stripped[7:].strip())
    return None


class CodeMissions:
    def __init__(self, session, store=None, runner=run_task, confirm=None):
        self.session = session
        self.store = store if store is not None else MissionStore()
        self.runner = runner
        self.confirm = confirm

    def handle(self, text, source, *, cancelled=lambda: False):
        if source not in {'text', 'voice'}:
            raise PermissionError('Seule une demande locale peut lancer du code.')
        parsed = command(text)
        if parsed is None:
            raise ValueError('Commande de mission inconnue.')
        kind, value = parsed
        if kind == 'list':
            rows = self.store.list()
            return 'Aucune mission de code.' if not rows else '\n'.join(
                f"{row['id']} : {row['state']} ({row['attempts']} essai(s)) - {row['goal']}" for row in rows)
        if kind == 'show':
            mission = self.store.get(value)
            files = ', '.join(mission['result'].get('changed_files', [])) or 'aucun'
            return f"Mission {value} : {mission['state']}. Fichiers changes : {files}."
        if kind == 'apply':
            from code_promotion import apply
            from codex_link import _workspace
            mission = self.store.get(value)
            if mission['state'] != 'executed' or not mission['source'] or self.confirm is None:
                raise ValueError('Cette mission ne peut pas etre appliquee.')
            folder = _workspace(mission['workspace'])
            if not apply(value, mission['source'], mission['source_sha'],
                         folder, self.confirm):
                return 'Application annulee ; le fichier original est conserve.'
            self.store.mark_applied(value)
            return f"Mission {value} appliquee au laboratoire avec copie de retour. Redemarre Alice pour charger ce module."
        if kind == 'restore':
            from code_promotion import restore
            from codex_link import _workspace
            mission = self.store.get(value)
            if mission['state'] != 'applied' or not mission['source'] or self.confirm is None:
                raise ValueError('Cette mission ne peut pas etre restauree.')
            folder = _workspace(mission['workspace'])
            if not restore(value, mission['source'], mission['source_sha'], folder, self.confirm):
                return 'Restauration annulee ; le fichier actuel est conserve.'
            self.store.mark_restored(value)
            return f"Mission {value} restauree. Redemarre Alice pour recharger l ancienne version."
        if kind == 'new_file':
            from code_promotion import stage
            source, prompt = value
            contents, digest = stage(source)
            mission = self.store.create('Modifie uniquement '+source+'. Demande : '+prompt,
                                        source=source, source_sha=digest,
                                        source_bytes=contents)
        else:
            mission = self.store.create(value) if kind == 'new' else self.store.get(value)
        mission = self.store.start(mission['id'])
        try:
            result = self.runner(self.session, mission['prompt'], Path(mission['workspace']),
                                 timeout=240, cancelled=cancelled)
        except (OSError, RuntimeError, PermissionError, ValueError) as error:
            result = {'status':'failed', 'changed_files':[], 'message':type(error).__name__}
            mission = self.store.finish(mission['id'], result)
            return f"Mission {mission['id']} arretee : {error}"
        mission = self.store.finish(mission['id'], result)
        files = ', '.join(result['changed_files']) or 'aucun'
        if mission['state'] == 'executed':
            summary = result.get('message', '').strip()
            return (f"Mission {mission['id']} executee dans {mission['workspace']}. "
                    f"Fichiers changes : {files}. "
                    'Le resultat doit encore etre verifie avant utilisation dans le vrai projet.'
                    + ('\nCompte rendu de l agent, non verifie : ' + summary if summary else ''))
        return f"Mission {mission['id']} : {mission['state']}. Fichiers changes : {files}."


def run_code_turn(app, text, source):
    epoch = app.speech_epoch
    cancelled = lambda: (app.stop.is_set() or not app.inputs.empty()
                         or app.session.voice.interruption_epoch != epoch)
    reply = app.code_missions.handle(text, source, cancelled=cancelled)
    app.events.put(('text', ('Mission de code', reply)))
    return reply
