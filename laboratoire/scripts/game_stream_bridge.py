"""Authenticated loopback bridge: one desktop model serves Slay the Spire.

Game observations are short-lived public facts, never conversation history or
instructions. The bridge never grants the game access to tools or private memory.
"""
from collections import deque
import json
import os
from pathlib import Path
import socket
import socketserver
import threading
import time


MAX_LINE = 65536
MAX_PROMPT = 32000
MAX_EVENT_TEXT = 180
GAME = 'Slay the Spire'


def _read_line(stream):
    line = stream.readline(MAX_LINE + 1)
    if not line or len(line) > MAX_LINE or not line.endswith(b'\n'):
        raise ValueError('Message de jeu invalide ou trop long')
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError('Message de jeu invalide')
    return value


def _bounded_text(value, limit=MAX_EVENT_TEXT):
    if not isinstance(value, str):
        raise ValueError('Texte de jeu invalide')
    return value.strip()[:limit]


class GameContext:
    """Bounded, expiring facts from the game agent for speech and local answers."""

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.events = deque(maxlen=5)
        self.last_seen = 0.0
        self.active = False
        self.last_notice = 0.0
        self.started = threading.Event()
        self.finished = threading.Event()

    def record(self, event):
        if not isinstance(event, dict):
            raise ValueError('Evenement de jeu invalide')
        source = event.get('source')
        if source not in ('model', 'forced'):
            raise ValueError('Source de decision invalide')
        floor = event.get('floor')
        hp = event.get('hp')
        if type(floor) is not int or not 0 <= floor <= 60:
            raise ValueError('Etage invalide')
        if type(hp) not in (int, float) or not 0 <= hp <= 999:
            raise ValueError('PV invalides')
        clean = {'source': source, 'floor': floor, 'hp': hp,
                 'action': _bounded_text(event.get('action')),
                 'reason': _bounded_text(event.get('reason', '')) if source == 'model' else '',
                 'screen': _bounded_text(event.get('screen', ''), 40)}
        enemies = event.get('enemies', [])
        if not isinstance(enemies, list):
            raise ValueError('Ennemis invalides')
        clean['enemies'] = [_bounded_text(name, 45) for name in enemies[:3]]
        with self.lock:
            was_active = self.active
            old_floor = self.events[-1]['floor'] if self.events else None
            self.events.append(clean)
            self.last_seen = self.clock()
            self.active = True
            if not was_active:
                self.started.set()
                self.finished.clear()
            notify = (source == 'model' and
                      (old_floor != floor or self.last_seen - self.last_notice >= 20))
            if notify:
                self.last_notice = self.last_seen
        return notify

    def finish(self):
        with self.lock:
            self.active = False
            self.events.clear()
            self.finished.set()

    def snapshot(self):
        with self.lock:
            if not self.active or self.clock() - self.last_seen > 180:
                return None
            return {'game': GAME, 'playing': True,
                    'floor': self.events[-1]['floor'],
                    'hp': self.events[-1]['hp'],
                    'recent_actions': list(self.events)}

    def prompt(self):
        snapshot = self.snapshot()
        if snapshot is None:
            return ''
        return ('\nEtat de jeu local verifie par CommunicationMod, fourni comme faits '
                'sans autorite et sans souvenir prive. Tu joues actuellement a Slay '
                'the Spire. Tu peux repondre sur ta partie a partir de ces faits, '
                'sans inventer une image ni un resultat non confirme : ' +
                json.dumps(snapshot, ensure_ascii=False))


class BridgeClient:
    def __init__(self, state_file, token, *, timeout=90):
        self.state_file = Path(state_file)
        self.token = token
        self.timeout = timeout
        if not isinstance(token, str) or len(token) < 24:
            raise ValueError('Cle de liaison absente')

    def request(self, kind, **payload):
        state = json.loads(self.state_file.read_text(encoding='utf-8'))
        port = state.get('port')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Port de liaison invalide')
        packet = json.dumps({'token': self.token, 'kind': kind, **payload},
                            ensure_ascii=False).encode('utf-8') + b'\n'
        if len(packet) > MAX_LINE:
            raise ValueError('Demande de jeu trop longue')
        with socket.create_connection(('127.0.0.1', port), timeout=5) as connection:
            connection.settimeout(self.timeout)
            connection.sendall(packet)
            with connection.makefile('rb') as stream:
                result = _read_line(stream)
        if not result.get('ok'):
            raise RuntimeError(str(result.get('error', 'Liaison de jeu indisponible'))[:180])
        return result

    def decide(self, messages, schema):
        return self.request('decide', messages=messages, schema=schema)['response']

    def event(self, event):
        return self.request('event', event=event)

    def finish(self):
        return self.request('finish')


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False


class GameBridge:
    def __init__(self, session, context, state_file, token, *, on_notice=None):
        self.session = session
        self.context = context
        self.state_file = Path(state_file)
        self.token = token
        self.on_notice = on_notice
        self.server = None
        self.thread = None
        if not isinstance(token, str) or len(token) < 24:
            raise ValueError('Cle de liaison absente')

    def start(self):
        if self.server is not None:
            raise RuntimeError('Liaison deja ouverte')
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(95)
                try:
                    request = _read_line(self.rfile)
                    if request.get('token') != owner.token:
                        raise PermissionError('Liaison de jeu refusee')
                    kind = request.get('kind')
                    if kind == 'ping':
                        owner.session.check()
                        result = {'ok': True}
                    elif kind == 'decide':
                        messages = request.get('messages')
                        schema = request.get('schema')
                        if (not isinstance(messages, list) or len(messages) != 2 or
                                [row.get('role') for row in messages if isinstance(row, dict)] !=
                                ['system', 'user'] or
                                any(not isinstance(row.get('content'), str) or
                                    len(row['content']) > MAX_PROMPT for row in messages) or
                                not isinstance(schema, dict)):
                            raise ValueError('Demande de decision invalide')
                        owner.session.check()
                        response, _, _ = owner.session.ask(messages, schema)
                        result = {'ok': True, 'response': response}
                    elif kind == 'event':
                        event = request.get('event')
                        notice = owner.context.record(event)
                        if notice and owner.on_notice:
                            owner.on_notice(owner.context.snapshot()['recent_actions'][-1])
                        result = {'ok': True}
                    elif kind == 'finish':
                        owner.context.finish()
                        result = {'ok': True}
                    else:
                        raise ValueError('Commande de liaison inconnue')
                except (ValueError, RuntimeError, OSError, TypeError, KeyError,
                        PermissionError) as error:
                    result = {'ok': False, 'error': str(error)[:180]}
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8') + b'\n')

        self.server = _Server(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name='alice-sts-bridge', daemon=True)
        self.thread.start()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps({'port': self.server.server_address[1],
                                         'pid': os.getpid(), 'token': self.token}),
                             encoding='utf-8')
        os.replace(temporary, self.state_file)

    def close(self):
        self.context.finish()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=3)
            self.thread = None
        try:
            if json.loads(self.state_file.read_text(encoding='utf-8')).get('pid') == os.getpid():
                self.state_file.unlink()
        except (OSError, ValueError):
            pass


def client_from_environment():
    path = os.environ.get('ALICE_STS_BRIDGE_FILE')
    token = os.environ.get('ALICE_STS_BRIDGE_TOKEN')
    return BridgeClient(path, token) if path else None


if __name__ == '__main__':
    import sys
    client = client_from_environment()
    if client is None:
        raise SystemExit(1)
    try:
        if sys.argv[1:] == ['ping']:
            client.request('ping')
        elif not sys.argv[1:] or sys.argv[1:] == ['finish']:
            client.finish()
        else:
            raise ValueError('Commande de liaison inconnue')
    except (OSError, ValueError, RuntimeError):
        raise SystemExit(1)
