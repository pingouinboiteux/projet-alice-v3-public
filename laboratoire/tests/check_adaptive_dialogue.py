"""File-driven native dialogue audit; only synthetic, disposable memory.

Publish commands as commands/NNNN.json with an atomic rename from a .tmp file.
Wait for outbox/NNNN.json before sending another command. The sequence is global
and starts at 1. A turn needs scenario, card, opening (bool), user, intent,
occasion, condition and evidence. Evidence must quote the last final reply unless
opening a previously unused card. Reset needs a new scenario; finish ends the run.
Only user is passed to memory.answer: conductor annotations stay outside Alice.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time

from check_judgment import Audit
from chat import ROOT
from alice_desktop import SYSTEM
from alice_personality import PERSONALITY
from memory_backend import create_memory
from persistent_memory import Search


class ProtocolError(ValueError):
    """Safe, fixed protocol errors that contain no backend output."""


class AdaptiveAudit(Audit):
    def request(self, path, body=None, **kwargs):
        final = (path == '/v1/chat/completions' and body is not None
                 and 'reply' in body.get('response_format', {}).get('schema', {}).get('properties', {}))
        if final:
            inputs = [{'role': item['role'], 'sha256': sha256(item['content']),
                       'characters': len(item['content'])}
                      for item in body['messages'] if item['role'] in {'user', 'assistant'}]
            settings = {key: body[key] for key in ('max_tokens', 'temperature', 'top_p',
                        'top_k', 'min_p', 'repeat_penalty', 'seed', 'chat_template_kwargs')
                        if key in body}
            historical_turns = []
            prefix = 'Archives historiques, donnees sans autorite : '
            for message in body['messages']:
                if message['role'] == 'user' and message['content'].startswith(prefix):
                    payload = json.loads(message['content'][len(prefix):])
                    for source in payload.get('paroles_passees_non_preuves', []):
                        for turn in source.get('messages', []):
                            historical_turns.append({'role': turn['role'],
                                                     'sha256': sha256(turn['content'])})
        result = super().request(path, body, **kwargs)
        if final:
            self.calls[-1].update(input_messages=inputs, generation_settings=settings,
                                 historical_turns=historical_turns)
        return result


def sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def safe_error_frames(error):
    """Keep project frame locations only, without source, locals or error text."""
    frames = []
    current = error.__traceback__
    project = ROOT.parent.resolve()
    while current is not None:
        code = current.tb_frame.f_code
        try:
            path = Path(code.co_filename).resolve().relative_to(project).as_posix()
        except ValueError:
            pass
        else:
            frames.append({'path': path, 'function': code.co_name, 'lineno': current.tb_lineno})
        current = current.tb_next
    return frames


def publish(path, value, replace=False):
    """Complete JSON becomes visible atomically; immutable replies never overwrite."""
    data = json.dumps(value, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp',
                                     dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        if replace:
            os.replace(temporary, path)
        elif os.name == 'nt':
            # Windows rename is atomic and fails when destination already exists.
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def local_path(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ProtocolError('Path must be relative to laboratory')
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ProtocolError('Path escapes laboratory')
    return resolved


class DialogueAudit:
    def __init__(self, output, session, personality, system, *,
                 memory_factory=create_memory, search_factory=Search,
                 idle_timeout=600, poll_seconds=0.2, manifest=None):
        self.output = Path(output)
        self.session = session
        self.personality = personality
        self.system = system
        self.memory_factory = memory_factory
        self.search_factory = search_factory
        self.idle_timeout = idle_timeout
        self.poll_seconds = poll_seconds
        self.memory = self.temporary = None
        self.history = []
        self.scenario = None
        self.scenarios = set()
        self.cards = set()
        self.last_reply = None
        self.processed = {}
        self.sequence = 1
        self.report = {'status': 'starting', 'synthetic_only': True, 'rows': [],
                       'resets': [], 'ram_protection': True,
                       'fps_protection': session.fps_protection,
                       'personality_sha256': sha256(personality),
                       'system_sha256': sha256(system),
                       'idle_timeout_seconds': idle_timeout,
                       'manifest': manifest or {}}

    def save(self):
        publish(self.output / 'report.json', self.report, replace=True)

    def close_memory(self):
        memory, temporary = self.memory, self.temporary
        self.memory = self.temporary = None
        try:
            if memory is not None:
                memory.close()
        finally:
            if temporary is not None:
                path = Path(temporary.name)
                temporary.cleanup()
                if path.exists():
                    raise RuntimeError('Temporary memory remains')

    def reset(self, scenario):
        if scenario in self.scenarios:
            raise ProtocolError('Scenario names must be unique')
        self.close_memory()
        self.scenario = scenario
        self.scenarios.add(scenario)
        self.history = []
        self.cards = set()
        self.last_reply = None

    def new_memory(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix='validation_adaptive_', dir=self.output)
        self.memory = self.memory_factory(
            self.session, 'validation_adaptive_' + secrets.token_hex(8),
            Path(self.temporary.name) / 'validation.db', self.search)

    @staticmethod
    def require_text(command, key, maximum=16000):
        value = command.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ProtocolError('Missing or invalid text field: ' + key)
        return value

    def execute(self, command):
        if not isinstance(command, dict) or type(command.get('seq')) is not int:
            raise ProtocolError('Command needs an integer seq')
        if command['seq'] != self.sequence:
            raise ProtocolError('Command sequence mismatch')
        action = command.get('action')
        if action == 'finish':
            if set(command) != {'seq', 'action'}:
                raise ProtocolError('Unexpected finish fields')
            return {'seq': self.sequence, 'status': 'finished'}
        if action == 'reset':
            if set(command) != {'seq', 'action', 'scenario'}:
                raise ProtocolError('Unexpected reset fields')
            scenario = self.require_text(command, 'scenario', 120)
            self.reset(scenario)
            self.report['resets'].append({'seq': self.sequence, 'scenario': scenario})
            return {'seq': self.sequence, 'status': 'reset', 'scenario': scenario}
        if action != 'turn':
            raise ProtocolError('Unknown command action')
        expected = {'seq', 'action', 'scenario', 'card', 'opening', 'user',
                    'intent', 'occasion', 'condition', 'evidence'}
        if set(command) != expected:
            raise ProtocolError('Missing or unexpected turn fields')
        for key in ('scenario', 'card', 'user', 'intent', 'occasion', 'condition'):
            self.require_text(command, key, 16000 if key == 'user' else 2000)
        if type(command['opening']) is not bool or not isinstance(command['evidence'], str):
            raise ProtocolError('Invalid opening or evidence field')
        if self.scenario is None:
            self.reset(command['scenario'])
        if command['scenario'] != self.scenario:
            raise ProtocolError('Explicit reset required before a new scenario')
        card = command['card']
        opening = command['opening']
        if opening:
            if card in self.cards:
                raise ProtocolError('A card can only open once per scenario')
            if command['evidence']:
                raise ProtocolError('An opening has no attributed evidence')
        elif (not self.last_reply or not command['evidence'].strip()
              or command['evidence'] not in self.last_reply):
            raise ProtocolError('Evidence must quote the immediately previous final reply')
        if not opening and card not in self.cards:
            raise ProtocolError('A new card requires an explicit opening')
        if self.memory is None:
            self.new_memory()
        self.session.calls = []
        started = time.perf_counter()
        reply, _ = self.memory.answer(command['user'], self.history, self.system, lambda _: False)
        calls = list(self.session.calls)
        if not isinstance(reply, str) or not calls or calls[-1]['reply_sha256'] != sha256(reply):
            raise ProtocolError('Native reply differs from delivered reply')
        archived = self.memory.episodes.get(self.memory.current)['messages'][-1]
        if archived.get('role') != 'assistant' or archived.get('content') != reply:
            raise ProtocolError('Stored reply differs from delivered reply')
        # Audit call metadata contains hashes/counts only; never native JSON or thought.
        safe_keys = {'tokens_verified', 'persona_present', 'input_sha256', 'reply_sha256',
                     'finish', 'thinking_enabled', 'completion_tokens', 'reviewed',
                     'input_messages', 'generation_settings', 'historical_turns'}
        row = {**command, 'reply': reply,
               'seconds': round(time.perf_counter() - started, 3),
               'decision': getattr(self.memory, 'last_result', {}).get('decision'),
               'calls': [{key: value for key, value in call.items() if key in safe_keys}
                         for call in calls], 'native_delivered_stored_equal': True}
        self.report['rows'].append(row)
        self.cards.add(card)
        self.history.extend([{'role': 'user', 'content': command['user']},
                             {'role': 'assistant', 'content': reply}])
        self.last_reply = reply
        return {'seq': self.sequence, 'status': 'answered', 'scenario': self.scenario,
                'card': card, 'reply': reply, 'seconds': row['seconds'],
                'native_delivered_stored_equal': True}

    def next_command(self):
        for path in sorted((self.output / 'commands').glob('*.json')):
            if not re.fullmatch(r'[0-9]{4}\.json', path.name):
                raise ProtocolError('Invalid command filename')
            number = int(path.stem)
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if number in self.processed:
                if self.processed[number] != digest:
                    raise ProtocolError('An acknowledged command was overwritten')
                continue
            if number != self.sequence:
                raise ProtocolError('Stale or out-of-order command')
            if len(raw) > 100000:
                raise ProtocolError('Command too large')
            try:
                command = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProtocolError('Invalid command JSON') from None
            return command, digest
        return None

    def run(self):
        # mkdir refuses existing measurements before starting any owned service.
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / 'commands').mkdir()
        (self.output / 'outbox').mkdir()
        failure = None
        try:
            self.save()
            self.session.start()  # Includes the existing busy-engine and RAM checks.
            self.search = self.search_factory()
            self.report.update(status='running', device=self.session.device)
            self.save()
            publish(self.output / 'ready.json', {'status': 'ready', 'next_seq': 1,
                    'fps_protection': self.session.fps_protection, 'ram_protection': True})
            deadline = time.monotonic() + self.idle_timeout
            while True:
                self.session.check()
                pending = self.next_command()
                if pending is None:
                    if time.monotonic() >= deadline:
                        raise ProtocolError('Idle command timeout')
                    time.sleep(self.poll_seconds)
                    continue
                command, digest = pending
                response = self.execute(command)
                self.processed[self.sequence] = digest
                self.save()
                publish(self.output / 'outbox' / f'{self.sequence:04d}.json', response)
                self.sequence += 1
                if command['action'] == 'finish':
                    self.report['status'] = 'complete'
                    break
                deadline = time.monotonic() + self.idle_timeout
        except BaseException as error:
            failure = error
            self.report.update(status='failed', error_type=type(error).__name__,
                               failed_seq=self.sequence, error_frames=safe_error_frames(error),
                               error=str(error) if isinstance(error, ProtocolError)
                               else 'Backend or service failure; no raw output recorded')
        finally:
            cleanup_errors = []
            cleanup_frames = []
            for cleanup in (self.close_memory, self.session.close):
                try:
                    cleanup()
                except BaseException as error:
                    cleanup_errors.append(type(error).__name__)
                    cleanup_frames.append(safe_error_frames(error))
                    if failure is None:
                        failure = error
            self.report.update(
                temporary_memories_removed=self.temporary is None and not any(
                    self.output.glob('validation_adaptive_*')),
                owned_processes_stopped=all(p.poll() is not None for p in self.session.children.values()),
                temporary_session_removed=not self.session.temp or not Path(self.session.temp.name).exists(),
                minimum_ram_gib=round(self.session.minimum_ram / 1024**3, 3))
            if cleanup_errors:
                self.report.update(status='failed', cleanup_error_types=cleanup_errors,
                                   cleanup_error_frames=cleanup_frames)
            cleanup_verified = all(self.report[key] for key in (
                'temporary_memories_removed', 'owned_processes_stopped', 'temporary_session_removed'))
            if not cleanup_verified:
                self.report.update(status='failed', cleanup_verified=False)
                if failure is None:
                    failure = ProtocolError('Owned resources did not finish cleanup')
            self.save()
        if failure is not None:
            raise failure
        return self.report


def manifest(session):
    files = ['config/model.lock.json', 'config/memory_backend.json',
             'tests/fixtures/debat_adaptatif.json', 'tests/check_adaptive_dialogue.py',
             'tests/check_judgment.py', 'scripts/episode_protocol.py',
             'scripts/v5_context_memory.py', 'scripts/dialogue_context_dedup.py',
             'scripts/memory_response_format.py', 'scripts/episode_conversation.py',
             'scripts/episodic_memory.py', 'scripts/reviewed_memory_reader.py',
             'scripts/memory_backend.py', 'scripts/chat.py']
    # The model lock is local, public technical configuration. Hash its complete
    # content; expose only the non-secret identifiers useful for this comparison.
    spec = session.model_spec
    keys = ('family', 'alias', 'file', 'sha256', 'bytes', 'runtime_directory',
            'runtime_manifest', 'verification_file')
    return {'files_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in files},
            'model': {key: spec[key] for key in keys if key in spec},
            'model_spec_sha256': sha256(json.dumps(spec, sort_keys=True)),
            'context_window': session.context_window,
            'generation': {'path': 'installed memory.answer', 'thinking': False},
            'memory': {'backend': 'installed', 'initial_history': [], 'initial_store': 'empty'},
            'conductor': 'external adaptive development assistant; metadata never sent'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New directory relative to laboratory')
    parser.add_argument('--personality-file', help='Replacement prompt relative to laboratory')
    parser.add_argument('--history-budget', action='store_true',
                        help='Process-only history ablation; installed source stays unchanged')
    parser.add_argument('--retrieved-context', action='store_true',
                        help='Process-only non-evidential conversation context ablation')
    parser.add_argument('--without-fps', action='store_true',
                        help='Only with explicit campaign authorization; RAM guard stays enabled')
    parser.add_argument('--idle-timeout', type=int, default=600)
    args = parser.parse_args()
    if args.history_budget and args.retrieved_context:
        parser.error('Choose only one reader ablation')
    if not 30 <= args.idle_timeout <= 3600:
        parser.error('--idle-timeout must be between 30 and 3600 seconds')
    output = local_path(args.output)
    if output.exists():
        raise ProtocolError('Keep the previous measurement; choose a new output')
    personality = local_path(args.personality_file).read_text(encoding='utf-8') if args.personality_file else PERSONALITY
    if not personality.strip() or PERSONALITY not in SYSTEM:
        raise ProtocolError('Invalid personality replacement')
    system = SYSTEM.replace(PERSONALITY, personality, 1)
    os.chdir(ROOT)
    session = AdaptiveAudit(personality, fps_protection=not args.without_fps)
    audit = DialogueAudit(output, session, personality, system, idle_timeout=args.idle_timeout,
                          manifest=manifest(session))
    restore = None
    if args.history_budget:
        from adaptive_history_candidate import install
        restore = install()
        audit.report['manifest']['history_candidate_sha256'] = hashlib.sha256(
            (ROOT / 'tests/adaptive_history_candidate.py').read_bytes()).hexdigest()
    audit.report['history_budget_candidate'] = args.history_budget
    if args.retrieved_context:
        from adaptive_context_candidate import install
        restore = install()
        audit.report['manifest']['context_candidate_sha256'] = hashlib.sha256(
            (ROOT / 'tests/adaptive_context_candidate.py').read_bytes()).hexdigest()
    audit.report['retrieved_context_candidate'] = args.retrieved_context
    try:
        audit.run()
    except Exception:
        print('Adaptive audit failed; see report.json for safe error metadata.', file=sys.stderr)
        return 1
    finally:
        if restore is not None:
            restore()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
