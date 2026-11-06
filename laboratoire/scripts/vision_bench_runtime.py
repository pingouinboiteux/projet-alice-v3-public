"""Isolated visual qualification; never opens Alice's memory or active UI."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error

import psutil
import requests
from chat import ROOT, Session, Job, processes, GAMES, select_device, free_ram
from model_profile import verify_resources, template_settings
from gpu_inventory import inventory

REPORT_ROOT = ROOT / 'data/validation/validation_vision_20261105'
PROJECTOR_DIR = ROOT / 'models/vision'
REPO = 'ggml-org/gemma-4-26B-A4B-it-GGUF'
PROJECTOR_NAME = 'mmproj-gemma-4-26B-A4B-it-Q8_0.gguf'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def prepare():
    """Pin revision, size and SHA before fetching only the missing projector."""
    meta = requests.get(f'https://huggingface.co/api/models/{REPO}', timeout=30)
    meta.raise_for_status()
    revision = meta.json()['sha']
    listing = requests.get(f'https://huggingface.co/api/models/{REPO}/tree/{revision}', timeout=30)
    listing.raise_for_status()
    entry = next(x for x in listing.json() if x['path'] == PROJECTOR_NAME)
    expected = entry['lfs']['oid']
    size = entry['size']
    available = shutil.disk_usage(ROOT).free
    if available < 2 * size + 2 * 1024**3:
        raise RuntimeError('Insufficient disk reserve')
    PROJECTOR_DIR.mkdir(parents=True, exist_ok=True)
    target = PROJECTOR_DIR / PROJECTOR_NAME
    url = f'https://huggingface.co/{REPO}/resolve/{revision}/{PROJECTOR_NAME}'
    report = {'revision': revision, 'url': url, 'expected_sha256': expected,
              'bytes': size, 'disk_free_before': available,
              'path': target.relative_to(ROOT).as_posix()}
    save(REPORT_ROOT / 'download_plan.json', report)
    if not target.exists():
        partial = target.with_suffix('.download')
        digest = hashlib.sha256()
        count = 0
        with requests.get(url, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with partial.open('wb') as stream:
                for block in response.iter_content(8 * 1024**2):
                    stream.write(block); digest.update(block); count += len(block)
                    if count > size:
                        raise RuntimeError('Download larger than manifest')
        if count != size or digest.hexdigest() != expected:
            raise RuntimeError('Projector checksum mismatch; not activated')
        partial.replace(target)
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if target.stat().st_size != size or digest != expected:
        raise RuntimeError('Existing projector mismatch')
    report.update(sha256=digest, verified=True)
    save(REPORT_ROOT / 'projector.json', report)
    print(json.dumps(report), flush=True)


class VisualSession(Session):
    """Test-only start, sharing production resource verification and RAM guard."""
    def __init__(self, image_tokens=None):
        super().__init__(allow_game=True, fps_protection=True, context_window=16384)
        self.image_tokens = image_tokens

    def start(self):
        names = processes()
        if 'llama-server.exe' in names:
            raise RuntimeError('Existing model active; not stopping it')
        if free_ram() < 6 * 1024**3:
            raise RuntimeError('Less than 6 GiB RAM free')
        # Latest user constraint: protect LoL at 60 FPS, overriding old exceptions.
        self.games_present = sorted(GAMES & names)
        if self.games_present:
            from vision_fps_guard import VisionFPSGuard
            probe = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            self.children['stop_probe'] = probe
            self.stop_owned()
            if probe.poll() is None: raise RuntimeError('Stop callback failed')
            self.children.pop('stop_probe')
            self.stop_control_verified = True
            self.frame_guard = VisionFPSGuard(self.stop_owned, REPORT_ROOT / 'fps_guard.json')
            self.frame_guard.start()
        model, engine = verify_resources(self.model_spec)
        projector = PROJECTOR_DIR / PROJECTOR_NAME
        manifest = json.loads((REPORT_ROOT / 'projector.json').read_text(encoding='utf-8'))
        with projector.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != manifest['sha256']:
            raise RuntimeError('Projector changed')
        self.device = select_device()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.key = secrets.token_hex(32)
        REPORT_ROOT.mkdir(parents=True, exist_ok=True)
        # Reuse the workers' already validated private-output root, not the
        # persistent measurement folder. Temporary audio is deleted on close.
        private_logs = ROOT / 'data/logs'
        private_logs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='validation_visual_', dir=private_logs)
        temporary = Path(self.temp.name)
        keyfile = temporary / 'key.txt'; keyfile.write_text(self.key)
        self.log = (temporary / 'server.log').open('w', encoding='utf-8')
        # Windows resolves the executable before applying cwd. Use the verified
        # resolved executable, never the other installation's same relative name.
        command = [str(engine), '-m', str(model.relative_to(ROOT)),
                   '--mmproj', str(projector.relative_to(ROOT)), '--mmproj-device', self.device,
                   '--device', self.device, '-ngl', '99', '-c', '16384', '-np', '1',
                   '-t', '1', '-tb', '1', '--cache-ram', '0', '--load-mode', 'dio',
                   '--offline', '--no-agent', '--no-webui', '--no-webui-mcp-proxy', '--verbosity', '4',
                   '--host', '127.0.0.1', '--port', str(port), '--api-key-file',
                   str(keyfile.relative_to(ROOT)), '--alias', self.model_spec['alias'],
                   '--jinja', '--reasoning-format', 'deepseek', '--chat-template-kwargs',
                   json.dumps(template_settings(self.model_spec))]
        if self.image_tokens is not None:
            if not 64 <= self.image_tokens <= 2048:
                raise ValueError('Visual token budget must be 64..2048')
            command += ['--image-max-tokens', str(self.image_tokens),
                        '--image-min-tokens', str(self.image_tokens),
                        '--ubatch-size', str(max(2048, self.image_tokens))]
        env = {k: v for k, v in os.environ.items() if not k.startswith(('LLAMA_ARG_', 'MTMD_'))}
        self.job = Job()
        self.check()
        self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=self.log,
                                       stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        self.job.assign(self.process); self.children['visual_model'] = self.process
        self.thread = threading.Thread(target=self.watch, daemon=True); self.thread.start()
        started = time.perf_counter()
        while time.perf_counter() - started < 180:
            self.check()
            try:
                self.request('/health', timeout=2)
                self.log.flush()
                text = (temporary / 'server.log').read_text(encoding='utf-8', errors='replace')
                layers = re.findall(r'offloaded (\d+)/(\d+) layers to GPU', text)
                if not layers or layers[-1][0] != layers[-1][1]:
                    raise RuntimeError('Full GPU model not confirmed')
                self.start_seconds = time.perf_counter() - started
                return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(.5)
        raise RuntimeError('Visual server timeout')


def strict_json(text):
    """No repair or substring extraction: malformed output is an instrument failure."""
    def reject(value):
        raise ValueError('Non-finite JSON value: ' + value)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed): raise ValueError('Non-finite JSON float')
        return parsed
    return json.loads(text, parse_constant=reject, parse_float=finite, object_pairs_hook=pairs)


def run(split, limit=0, image_tokens=None, with_voice=False, adapter='baseline'):
    from vision_bench_cases import generate_cases, request_for_case, score_case
    stamp = time.strftime('%H%M%S')
    path = REPORT_ROOT / f'{split}_{"voice_" if with_voice else ""}{stamp}.json'
    session = VisualSession(image_tokens)
    report = {'status': 'starting', 'split': split, 'adapter': adapter, 'image_max_tokens': image_tokens, 'with_voice': with_voice,
              'model': session.model_spec, 'adapters': inventory(), 'rows': [],
              'scope': 'synthetic images, direct model API; no production memory/audio/PC actions',
              'samples': []}
    done = threading.Event()
    voice_thread = None
    def monitor():
        while not done.wait(.25):
            try:
                p = psutil.Process(session.process.pid) if session.process else None
                report['samples'].append({'t': time.perf_counter(), 'free_ram': free_ram(),
                     'server_rss': p.memory_info().rss if p else 0})
            except psutil.Error:
                pass
    thread = threading.Thread(target=monitor, daemon=True); thread.start()
    try:
        session.start()
        report.update(status='running', startup_seconds=session.start_seconds,
                      device=session.device, games_present=session.games_present)
        if session.frame_guard:
            report['fps_guard_report'] = str(session.frame_guard.report_path.relative_to(ROOT))
            report['stop_control_verified'] = getattr(session, 'stop_control_verified', False)
        if with_voice:
            from voice_link import Voice
            session.voice = Voice(session)
            voice_start = time.perf_counter()
            session.voice.start()
            report['voice_start_seconds'] = time.perf_counter() - voice_start
            report['voice_profile'] = session.voice.profile_name
            # Exercise actual synthesis without opening audio output or microphone.
            tts_start = time.perf_counter()
            packets = 0
            for _path, _info in session.voice.audio_parts('Je regarde les formes et les mots de cette image de test.'):
                packets += 1
            report['silent_synthesis'] = {'seconds': time.perf_counter()-tts_start, 'packets': packets}
        if split == 'desktop':
            from vision_desktop_cases import generate_cases as make_cases
        else:
            make_cases = generate_cases
        cases = make_cases(REPORT_ROOT / 'images' / split, split)
        if limit: cases = cases[:limit]
        if with_voice:
            def concurrent_voice():
                state = report['concurrent_synthesis']
                state['started'] = time.perf_counter()
                try:
                    for _path, _info in session.voice.audio_parts(
                            'Je distingue les formes, puis je verifie leur position avant de proposer une action. Une information manquante reste inconnue.'):
                        state['packets'] += 1
                    state['status'] = 'complete'
                except Exception as error:
                    state.update(status='failed', error=str(error))
                finally:
                    state['ended'] = time.perf_counter()
            report['concurrent_synthesis'] = {'status': 'running', 'packets': 0}
            voice_thread = threading.Thread(target=concurrent_voice, daemon=True)
            voice_thread.start()
        for case in cases:
            visible = request_for_case(case)
            if adapter == 'native':
                from vision_observation_adapter import build_question
                visible['question'] = build_question(case)
            started = time.perf_counter()
            image = base64.b64encode(Path(visible['image_path']).read_bytes()).decode('ascii')
            encode_ms = (time.perf_counter() - started) * 1000
            payload = {'messages': [
                {'role': 'system', 'content': 'Analyse uniquement cette image de test. N invente pas les informations absentes. Suis le format JSON demande.'},
                {'role': 'user', 'content': [
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image}},
                    {'type': 'text', 'text': visible['question']}]}],
                'temperature': 0, 'seed': 62421, 'max_tokens': 256,
                'chat_template_kwargs': template_settings(session.model_spec),
                'response_format': {'type': 'json_object'}}
            row = {'id': case['id'], 'category': case['category'], 'encode_ms': encode_ms,
                   'expected': case['expected']}
            call = time.perf_counter()
            row['started'] = call
            try:
                result = session.request('/v1/chat/completions', payload, timeout=180)
                row['request_ms'] = (time.perf_counter() - call)*1000
                choice = result['choices'][0]
                row.update(content=choice['message'].get('content'), finish=choice['finish_reason'],
                           usage=result.get('usage'), timings=result.get('timings'))
                parsed = strict_json(row['content'])
                if adapter == 'native':
                    from vision_observation_adapter import decode_response, score_board_set
                    from PIL import Image
                    with Image.open(visible['image_path']) as source_image:
                        dimensions = source_image.size
                    row['decoded'] = decode_response(case, parsed, image_size=dimensions)
                    row['score'] = score_case(case, row['decoded'])
                    if case['category'] == 'board_occupancy':
                        row['board_set'] = score_board_set(case, parsed)
                        row['score']['passed'] &= row['board_set']['passed']
                else:
                    row['score'] = score_case(case, parsed)
                if choice['finish_reason'] != 'stop': row['score']['passed'] = False
            except Exception as error:
                row.update(error=str(error), request_ms=(time.perf_counter()-call)*1000,
                           score={'passed': False})
            report['rows'].append(row); save(path, report)
            print(json.dumps({k:row[k] for k in ('id','category','request_ms','score')}), flush=True)
            session.check()
        report['status'] = 'complete'
    except Exception as error:
        report.update(status='failed', error=str(error))
        print('FAILED', str(error), flush=True)
    finally:
        try:
            if voice_thread:
                voice_thread.join(timeout=20)
                if voice_thread.is_alive():
                    report['status'] = 'voice_shutdown_failed'
                    session.stop_owned()
                    voice_thread.join(timeout=3)
                if report.get('concurrent_synthesis', {}).get('status') != 'complete':
                    report['status'] = 'concurrent_synthesis_failed'
        except Exception as error:
            report.update(status='cleanup_failed', concurrent_cleanup_error=str(error))
        done.set(); thread.join(2)
        try:
            if session.temp:
                session.log.flush()
                log = Path(session.temp.name) / 'server.log'
                if log.exists():
                    text = log.read_text(encoding='utf-8', errors='replace').replace(session.key, '[redacted]')
                    (REPORT_ROOT / (path.stem + '_server.log')).write_text(text, encoding='utf-8')
                voice_log = Path(session.temp.name) / 'voice.log'
                if voice_log.exists():
                    (REPORT_ROOT / (path.stem + '_voice.log')).write_text(
                        voice_log.read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
        except Exception as error:
            report['log_archive_error'] = str(error)
        finally:
            try:
                session.close()
            except Exception as error:
                report.update(status='cleanup_failed', session_cleanup_error=str(error))
        report['minimum_free_ram'] = session.minimum_ram
        report['owned_processes_stopped'] = all(p.poll() is not None for p in session.children.values())
        if not report['owned_processes_stopped']: report['status'] = 'cleanup_failed'
        report['passed'] = sum(r['score']['passed'] for r in report['rows'])
        save(path, report)
        print('REPORT', path.relative_to(ROOT), report['status'], report['passed'], '/', len(report['rows']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'calibration', 'heldout', 'desktop'])
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--image-tokens', type=int)
    parser.add_argument('--voice', action='store_true')
    parser.add_argument('--adapter', choices=['baseline','native'], default='baseline')
    args = parser.parse_args()
    if args.mode == 'prepare': prepare()
    else: run(args.mode, args.limit, args.image_tokens, args.voice, args.adapter)
