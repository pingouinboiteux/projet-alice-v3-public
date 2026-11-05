"""Exercise adaptive branching with divergent fake native replies, never an LLM."""
import json
from pathlib import Path
import threading
import time

import pytest

from check_adaptive_dialogue import AdaptiveAudit, Audit, DialogueAudit, ProtocolError, publish, safe_error_frames, sha256


class FakeSession:
    fps_protection = True
    device = 'fake'
    minimum_ram = 8 * 1024**3
    children = {}
    temp = None

    def __init__(self, startup_error=False):
        self.calls = []
        self.started = self.closed = False
        self.startup_error = startup_error

    def start(self):
        self.started = True
        if self.startup_error:
            raise RuntimeError('PRIVATE BACKEND PROMPT')

    def check(self):
        pass

    def close(self):
        self.closed = True


class FakeMemory:
    def __init__(self, session, replies, mismatch=None, close_error=False):
        self.session = session
        self.replies = iter(replies)
        self.mismatch = mismatch
        self.close_error = close_error
        self.closed = False
        self.current = 'validation_episode'
        self.episodes = self
        self.seen = []
        self.stored = None
        self.last_result = {'decision': {'route': 'general_discussion'},
                            'private': 'PRIVATE INTERNAL THOUGHT'}

    def answer(self, user, history, system, cancel):
        self.seen.append((user, list(history), system))
        if self.mismatch == 'answer_error':
            raise RuntimeError('PRIVATE BACKEND PROMPT')
        reply = next(self.replies)
        native = 'different native' if self.mismatch == 'native' else reply
        self.session.calls.append({'reply_sha256': sha256(native),
                                   'internal_secret': 'PRIVATE INTERNAL THOUGHT'})
        self.stored = 'different stored' if self.mismatch == 'stored' else reply
        return reply, {'private': 'PRIVATE INTERNAL THOUGHT'}

    def get(self, _):
        return {'messages': [{'role': 'assistant', 'content': self.stored}]}

    def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError('PRIVATE CLOSE ERROR')


def turn(seq=1, *, scenario='long', card='D1', evidence='', opening=True, user='Que soutiens-tu ?'):
    return {'seq': seq, 'action': 'turn', 'scenario': scenario, 'card': card,
            'opening': opening, 'evidence': evidence, 'user': user,
            'intent': 'Examiner sa raison', 'occasion': 'position',
            'condition': 'Une position est exprimee'}


def make_audit(tmp_path, replies=('Je distingue effet et intention.',), *,
               mismatch=None, close_error=False, session=None):
    session = session or FakeSession()
    memories = []
    databases = []

    def factory(session, profile, database, search):
        assert profile.startswith('validation_')
        assert database.name == 'validation.db'
        assert database.parent.name.startswith('validation_')
        database.write_text('synthetic isolated memory', encoding='utf-8')
        databases.append(database)
        memory = FakeMemory(session, replies, mismatch, close_error)
        memories.append(memory)
        return memory

    audit = DialogueAudit(tmp_path / 'measurement', session, 'validation personality',
                          'validation system', memory_factory=factory,
                          search_factory=lambda: object(), idle_timeout=2,
                          poll_seconds=0.005)
    return audit, memories, databases


class Running:
    """Use the real file protocol while fake memory lives in the server thread."""
    def __init__(self, audit):
        self.audit = audit
        self.error = None

        def target():
            try:
                audit.run()
            except BaseException as error:
                self.error = error
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()
        self.wait_for(audit.output / 'ready.json')

    def wait_for(self, path):
        deadline = time.monotonic() + 3
        while not path.exists():
            if self.error is not None:
                raise self.error
            assert time.monotonic() < deadline, f'Timed out waiting for {path.name}'
            time.sleep(0.005)
        return json.loads(path.read_text(encoding='utf-8'))

    def send(self, command):
        name = f"{command['seq']:04d}.json"
        publish(self.audit.output / 'commands' / name, command)
        return self.wait_for(self.audit.output / 'outbox' / name)

    def join(self):
        self.thread.join(timeout=4)
        assert not self.thread.is_alive(), 'Audit did not stop'


@pytest.mark.parametrize('first,followup', [
    ('Le contraste est un effet, pas une intention.', 'Pourquoi distinguer effet et intention ?'),
    ('Je ne peux pas choisir sans definir le createur.', 'Supposons un createur tout-puissant.')])
def test_divergent_replies_drive_actual_next_turn_and_keep_history(tmp_path, first, followup):
    audit, memories, databases = make_audit(tmp_path, (first, 'Une distinction utile.'))
    running = Running(audit)
    result = running.send(turn())
    assert result['reply'] == first
    second = running.send(turn(2, evidence=first, opening=False, user=followup))
    assert second['native_delivered_stored_equal']
    running.send({'seq': 3, 'action': 'finish'})
    running.join()
    assert running.error is None
    assert memories[0].seen[1] == (followup, [
        {'role': 'user', 'content': 'Que soutiens-tu ?'},
        {'role': 'assistant', 'content': first}], 'validation system')
    assert memories[0].closed and audit.session.closed
    assert not databases[0].exists()
    report = (audit.output / 'report.json').read_text(encoding='utf-8')
    assert 'PRIVATE' not in report
    assert json.loads(report)['temporary_memories_removed']
    assert json.loads(report)['rows'][0]['decision'] == {'route': 'general_discussion'}


@pytest.mark.parametrize('mismatch', ['native', 'stored', 'answer_error'])
def test_divergence_or_backend_error_fails_and_always_cleans(tmp_path, mismatch):
    audit, memories, databases = make_audit(tmp_path, mismatch=mismatch)
    running = Running(audit)
    publish(audit.output / 'commands' / '0001.json', turn())
    running.join()
    assert running.error is not None
    assert audit.report['status'] == 'failed'
    assert memories[0].closed and audit.session.closed
    assert not databases[0].exists()
    assert audit.report['rows'] == []
    assert 'PRIVATE' not in (audit.output / 'report.json').read_text(encoding='utf-8')
    frames = audit.report['error_frames']
    assert frames
    assert all(set(frame) == {'path', 'function', 'lineno'} for frame in frames)
    assert all(not Path(frame['path']).is_absolute() for frame in frames)
    assert audit.report['failed_seq'] == 1


def test_misattributed_evidence_cannot_reach_backend(tmp_path):
    audit, memories, databases = make_audit(tmp_path)
    running = Running(audit)
    running.send(turn())
    publish(audit.output / 'commands' / '0002.json',
            turn(2, evidence='Tu prouves une intention certaine.', opening=False))
    running.join()
    assert isinstance(running.error, ProtocolError)
    assert len(memories[0].seen) == 1
    assert not databases[0].exists()


def test_evidence_must_quote_latest_reply_not_an_older_turn(tmp_path):
    audit, memories, _ = make_audit(tmp_path, ('Premiere position.', 'Position corrigee.'))
    running = Running(audit)
    running.send(turn())
    running.send(turn(2, opening=False, evidence='Premiere position.'))
    publish(audit.output / 'commands' / '0003.json',
            turn(3, opening=False, evidence='Premiere position.'))
    running.join()
    assert isinstance(running.error, ProtocolError)
    assert len(memories[0].seen) == 2


def test_explicit_reset_gets_new_database_and_empty_history(tmp_path):
    audit, memories, databases = make_audit(tmp_path)
    running = Running(audit)
    running.send(turn())
    running.send({'seq': 2, 'action': 'reset', 'scenario': 'mini-D1'})
    assert memories[0].closed and not databases[0].exists()
    running.send(turn(3, scenario='mini-D1'))
    running.send({'seq': 4, 'action': 'finish'})
    running.join()
    assert running.error is None
    assert memories[1].seen[0][1] == []
    assert databases[0] != databases[1]
    assert all(memory.closed for memory in memories)
    assert all(not database.exists() for database in databases)


@pytest.mark.parametrize('bad', [
    turn(2, scenario='unannounced'),
    turn(2, opening=True),
    turn(2, card='D2', opening=False, evidence='Je distingue effet et intention.')])
def test_new_scenario_or_false_opening_rejected(tmp_path, bad):
    audit, memories, _ = make_audit(tmp_path)
    running = Running(audit)
    running.send(turn())
    publish(audit.output / 'commands' / '0002.json', bad)
    running.join()
    assert isinstance(running.error, ProtocolError)
    assert len(memories[0].seen) == 1


def test_new_card_can_open_without_claiming_a_previous_argument(tmp_path):
    audit, memories, _ = make_audit(tmp_path, ('Premiere.', 'Deuxieme.'))
    running = Running(audit)
    running.send(turn())
    running.send(turn(2, card='D2'))
    running.send({'seq': 3, 'action': 'finish'})
    running.join()
    assert running.error is None
    assert len(memories[0].seen[1][1]) == 2


@pytest.mark.parametrize('filename,command', [
    ('0000.json', turn(0)), ('0002.json', turn(2)), ('0001.json', turn(9))])
def test_stale_skipped_and_mismatched_sequence_fail_before_memory(tmp_path, filename, command):
    audit, memories, _ = make_audit(tmp_path)
    running = Running(audit)
    publish(audit.output / 'commands' / filename, command)
    running.join()
    assert isinstance(running.error, ProtocolError)
    assert not memories
    assert audit.session.closed


def test_acknowledged_command_cannot_be_overwritten(tmp_path):
    audit, memories, _ = make_audit(tmp_path)
    running = Running(audit)
    running.send(turn())
    publish(audit.output / 'commands' / '0001.json', turn(user='Autre question'), replace=True)
    running.join()
    assert isinstance(running.error, ProtocolError)
    assert len(memories[0].seen) == 1


def test_existing_output_and_immutable_reply_are_preserved(tmp_path):
    audit, _, _ = make_audit(tmp_path)
    audit.output.mkdir()
    previous = audit.output / 'previous.json'
    publish(previous, {'preserve': True})
    with pytest.raises(FileExistsError):
        audit.run()
    with pytest.raises(FileExistsError):
        publish(previous, {'preserve': False})
    assert json.loads(previous.read_text()) == {'preserve': True}
    assert not audit.session.started


def test_cleanup_continues_after_memory_close_failure(tmp_path):
    audit, memories, databases = make_audit(tmp_path, close_error=True)
    running = Running(audit)
    running.send(turn())
    running.send({'seq': 2, 'action': 'finish'})
    running.join()
    assert running.error is not None
    assert audit.report['status'] == 'failed'
    assert memories[0].closed and audit.session.closed
    assert not databases[0].exists()
    assert 'PRIVATE' not in (audit.output / 'report.json').read_text(encoding='utf-8')


def test_startup_failure_closes_session_and_redacts_backend_text(tmp_path):
    audit, memories, _ = make_audit(tmp_path, session=FakeSession(startup_error=True))
    with pytest.raises(RuntimeError):
        audit.run()
    assert audit.session.closed and not memories
    assert 'PRIVATE' not in (audit.output / 'report.json').read_text(encoding='utf-8')


def test_idle_timeout_closes_everything(tmp_path):
    audit, memories, _ = make_audit(tmp_path)
    audit.idle_timeout = 0.03
    with pytest.raises(ProtocolError, match='Idle'):
        audit.run()
    assert audit.session.closed and not memories
    assert audit.report['status'] == 'failed'


def test_input_instrument_records_only_hashes_of_final_user_assistant_messages(monkeypatch):
    session = object.__new__(AdaptiveAudit)
    session.calls = []

    def native_request(self, path, body=None, **kwargs):
        self.calls.append({'reply_sha256': sha256('Une reponse finale.')})
        return {'synthetic': True}

    monkeypatch.setattr(Audit, 'request', native_request)
    body = {'messages': [{'role': 'system', 'content': 'PRIVATE SYSTEM PROMPT'},
                         {'role': 'user', 'content': 'PRIVATE USER CONTEXT'},
                         {'role': 'assistant', 'content': 'PRIVATE PAST REPLY'}],
            'response_format': {'schema': {'properties': {'reply': {'type': 'string'}}}},
            'temperature': 0.7, 'max_tokens': 2048,
            'chat_template_kwargs': {'enable_thinking': False}}
    result = session.request('/v1/chat/completions', body)
    assert result == {'synthetic': True}
    assert session.calls[-1]['input_messages'] == [
        {'role': item['role'], 'sha256': sha256(item['content']),
         'characters': len(item['content'])} for item in body['messages'][1:]]
    assert session.calls[-1]['generation_settings']['temperature'] == 0.7
    assert 'PRIVATE' not in json.dumps(session.calls)


def test_error_frames_never_record_source_locals_or_external_paths():
    private_local = 'PRIVATE LOCAL DATA'
    try:
        exec(compile("raise ValueError('PRIVATE ERROR MESSAGE')", '/outside/PRIVATE_SOURCE.py', 'exec'))
    except ValueError as error:
        frames = safe_error_frames(error)
    assert private_local
    assert frames
    assert frames[-1]['function'] == 'test_error_frames_never_record_source_locals_or_external_paths'
    assert all(set(frame) == {'path', 'function', 'lineno'} for frame in frames)
    assert all(frame['path'].startswith('laboratoire/') for frame in frames)
    assert 'PRIVATE' not in json.dumps(frames)
