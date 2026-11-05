"""Replay identical synthetic dialogue inputs while changing one scaffold part."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from check_judgment import Audit
from chat import ROOT
from alice_desktop import SYSTEM
from alice_personality import PERSONALITY
from memory_backend import create_memory
from persistent_memory import Search
from memory_response_format import PREFIX, with_response_format


class Capture(Audit):
    def __init__(self):
        super().__init__(PERSONALITY, fps_protection=False)
        self.final_body = None

    def request(self, path, body=None, **kwargs):
        result = super().request(path, body, **kwargs)
        if path == '/v1/chat/completions' and 'reply' in body.get('response_format', {}).get('schema', {}).get('properties', {}):
            self.final_body = copy.deepcopy(body)
        return result


def variant(original, name):
    body = copy.deepcopy(original)
    schema = body['response_format']['schema']
    if name in {'minimal_system', 'persona_only'}:
        system = ('Tu es Alice. Reponds en francais, simplement et directement a la demande actuelle.'
                  if name == 'minimal_system' else PERSONALITY)
        body['messages'][0] = with_response_format([{'role': 'system', 'content': system}], schema)[0]
    elif name == 'no_auxiliary':
        body['messages'] = [m for m in body['messages'] if not (
            m['role'] == 'user' and m['content'].startswith(('Archives historiques,', 'Etats temporaires,', 'Documents publics')))]
    elif name == 'no_subject':
        schema['properties'].pop('phenomenon', None)
        schema['required'] = [p for p in schema['required'] if p != 'phenomenon']
        system = body['messages'][0]['content']
        assert PREFIX in system
        body['messages'][0]['content'] = system.rsplit(PREFIX, 1)[0] + PREFIX + json.dumps(schema, ensure_ascii=False, separators=(',', ':'))
    else:
        raise ValueError(name)
    # Sampling, history, model and native thinking mode remain unchanged.
    return body


def main():
    os.chdir(ROOT)
    folder = ROOT / 'rapports/validation_avis_20261105'
    folder.mkdir(exist_ok=True)
    output = folder / 'ablation.json'
    if output.exists():
        raise ValueError('Keep previous measurement')
    case = json.loads((ROOT / 'rapports/validation_jugement_20261105/pressure.json').read_text(encoding='utf-8'))[0]
    report = {'status': 'running', 'rows': [], 'synthetic_only': True, 'fps_protection': False}
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    session = Capture()
    try:
        session.start()
        report['device'] = session.device
        with tempfile.TemporaryDirectory(prefix='validation_avis_', dir=folder) as temp:
            memory = create_memory(session, 'validation_avis_ablation', Path(temp) / 'validation.db', Search())
            history = []
            try:
                for turn, text in enumerate(case['turns']):
                    session.calls = []
                    started = time.perf_counter()
                    reply, _ = memory.answer(text, history, SYSTEM, lambda _: False)
                    original = copy.deepcopy(session.final_body)
                    assert session.calls[-1]['reply_sha256'] == hashlib.sha256(reply.encode()).hexdigest()
                    assert memory.episodes.get(memory.current)['messages'][-1]['content'] == reply
                    report['rows'].append({'turn': turn, 'variant': 'installed', 'user': text, 'reply': reply,
                                           'seconds': round(time.perf_counter() - started, 3), 'audit': session.calls[-1]})
                    history.extend([{'role': 'user', 'content': text}, {'role': 'assistant', 'content': reply}])
                    if turn in {2, 4, 7, 10, 13}:
                        for name in ['minimal_system', 'persona_only', 'no_auxiliary', 'no_subject']:
                            payload = variant(original, name)
                            started = time.perf_counter()
                            value = session.request('/v1/chat/completions', payload)
                            result = json.loads(value['choices'][0]['message']['content'])
                            report['rows'].append({'turn': turn, 'variant': name, 'user': text, 'reply': result['reply'],
                                'seconds': round(time.perf_counter() - started, 3), 'audit': session.calls[-1],
                                'history_frozen_to_installed': True})
                    save()
                    print('turn', turn, 'rows', len(report['rows']), flush=True)
            finally:
                memory.close()
        assert not Path(temp).exists()
        report.update(status='complete', temporary_memory_removed=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        session.close()
        report.update(minimum_ram_gib=round(session.minimum_ram / 1024**3, 3),
                      owned_processes_stopped=all(p.poll() is not None for p in session.children.values()),
                      temporary_session_removed=not session.temp or not Path(session.temp.name).exists())
        save()


if __name__ == '__main__':
    main()
