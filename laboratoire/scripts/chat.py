"""Guarded local model transport. Standard library, Windows only."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from dxgi import enumerate_adapters
from vulkan import enumerate_devices
from model_profile import load_profile,template_settings,verify_resources
from memory_response_format import with_response_format,PREFIX

ROOT = Path(__file__).resolve().parents[1]
GAMES = {'league of legends.exe', 'tftclient-win64-shipping.exe',
         'cosmoteer.exe', 'echoes.exe', 'sineusarena.exe'}
SYSTEM = ('Tu es un assistant local en cours d evaluation. Reponds en francais. '
          'Tu ne disposes d aucun outil, acces aux fichiers, vision, audition ou '
          'memoire persistante. Ne pretends pas avoir effectue une action. '
          'Indique tes incertitudes. Aucune personnalite de personnage ne t est imposee.')


class Memory(ctypes.Structure):
    _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
        (n, ctypes.c_ulonglong) for n in ('total', 'available', 'page_total',
        'page_available', 'virtual_total', 'virtual_available', 'extended')]


def free_ram():
    value = Memory()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise OSError('RAM measurement failed')
    return value.available


def processes():
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('name', wintypes.WCHAR * 260)]
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        item = Entry()
        item.size = ctypes.sizeof(item)
        if not api.Process32FirstW(handle, ctypes.byref(item)):
            raise ctypes.WinError(ctypes.get_last_error())
        found = set()
        while True:
            found.add(item.name.lower())
            if not api.Process32NextW(handle, ctypes.byref(item)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(ctypes.get_last_error())
                break
        # This lab is for the user's desktop. A restricted execution environment
        # can show only its own children and falsely report no game. Require a
        # visible desktop witness; losing it must stop work, not relax the guard.
        if 'explorer.exe' not in found:
            raise RuntimeError('Session Windows non visible : mesure des jeux non fiable')
        return found
    finally:
        api.CloseHandle(handle)


def select_device():
    adapters = [a for a in enumerate_adapters()
                if a.subsystem_id == 0x240E1458 and not a.flags]
    if len(adapters) != 1:
        raise RuntimeError('Reserved GPU not uniquely identified')
    devices = [d for d in enumerate_devices()
               if d.luid_valid and d.luid == adapters[0].luid]
    if len(devices) != 1:
        raise RuntimeError('Vulkan GPU identity mismatch')
    return f'Vulkan{devices[0].index}'


class Job:
    """Windows closes the owned server even if the chat window is closed."""
    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                        ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ('ro', 'wo', 'oo', 'rt', 'wt', 'ot')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO)] + [(n, ctypes.c_size_t)
                        for n in ('process_memory', 'job_memory', 'peak_process', 'peak_job')]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                      ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.kill()
            process.wait()
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if getattr(self, 'handle', None):
            self.api.CloseHandle(self.handle)
            self.handle = None


class Session:
    def __init__(self, allow_game=False, context_window=8192, fps_protection=True, model_profile=None, ram_protection=True):
        self.model_spec = load_profile() if model_profile is None else dict(model_profile)
        self.context_window = context_window
        self.allow_game = allow_game
        self.fps_protection = fps_protection
        self.ram_protection = ram_protection
        self.children = {}
        self.frame_guard = None
        self.voice = None
        self.process = None
        self.job = None
        self.temp = None
        self.log = None
        self.reason = None
        self.minimum_ram = free_ram()
        self.done = threading.Event()
        self.thread = None
        self.stop_lock = threading.Lock()
        self.inference_lock = threading.RLock()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def check(self):
        if self.frame_guard:
            self.frame_guard.check()
        if self.reason:
            raise RuntimeError(self.reason)
        if self.process and self.process.poll() is not None:
            raise RuntimeError('Moteur arrete. Consulter le resultat du diagnostic.')

    def watch(self):
        tick = 0
        while not self.done.wait(0.5):
            try:
                value = free_ram()
                self.minimum_ram = min(value, self.minimum_ram)
                if self.ram_protection and value < 6 * 1024**3:
                    raise RuntimeError('Arret : moins de 6 Gio de RAM libre')
                tick += 1
                if self.fps_protection and tick % 4 == 0 and not self.frame_guard and GAMES & processes():
                    raise RuntimeError('Arret : un jeu connu a ete ouvert')
            except Exception as error:
                self.reason = str(error)
                self.stop_owned()
                print('\n' + self.reason, flush=True)
                return

    def request(self, path, body=None, timeout=120):
        self.check()
        payload = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request(self.url + path, data=payload,
              headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=timeout) as response:
            result = json.load(response)
        self.check()
        return result

    def start(self):
        if self.ram_protection and self.minimum_ram < 6 * 1024**3:
            raise RuntimeError('Au moins 6 Gio de RAM libre sont necessaires')
        names = processes()
        if GAMES & names and not self.allow_game:
            raise RuntimeError('Ferme le jeu avant ce premier laboratoire')
        if 'llama-server.exe' in names:
            raise RuntimeError('Un autre moteur est actif : ferme Alice ou le laboratoire precedent')
        spec = self.model_spec
        model,engine = verify_resources(spec)
        device = select_device()
        self.device = device
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.key = secrets.token_hex(32)
        temp_root = ROOT / 'logs'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='validation_session_', dir=temp_root)
        temp_path = Path(self.temp.name)
        key_path = temp_path / 'key.txt'
        key_path.write_text(self.key)
        self.log = (temp_path / 'server.log').open('w', encoding='utf-8')
        if self.fps_protection and GAMES & names:
            from types import SimpleNamespace
            from fps_guard import NativeGuard
            self.frame_guard = NativeGuard(
                SimpleNamespace(processes=self.children), temp_path.name,
                duration_seconds=1800, minimum_fps=60, focus_aware=True,
                baseline_seconds=5)
            self.frame_guard.stop_owned = self.stop_owned
            self.frame_guard.start()
        command = [engine.relative_to(ROOT).as_posix(), '-m', model.relative_to(ROOT).as_posix(),
                   '--host', '127.0.0.1', '--port', str(port), '--api-key-file',
                   key_path.relative_to(ROOT).as_posix(), '--device', device, '-ngl', '99',
                   '-c', str(self.context_window), '--alias', spec['alias'], '-t', '1', '-tb', '1', '-np', '1', '--cache-ram', '0',
                   '--load-mode', 'dio', '--offline', '--no-agent', '--verbosity', '4',
                   '--jinja', '--reasoning-format', 'deepseek', '--no-webui',
                   '--no-webui-mcp-proxy']
        # Direct clients such as Codex inherit the same native Gemma mode.
        command+=['--chat-template-kwargs',json.dumps(template_settings(spec))]
        env = {k: v for k, v in os.environ.items() if not k.startswith('LLAMA_ARG_')}
        self.job = Job()
        self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=self.log,
                        stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        self.job.assign(self.process)
        self.children['language_model'] = self.process
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            self.check()
            try:
                self.request('/health', timeout=2)
                if spec.get('require_full_gpu'):
                    import re
                    self.log.flush()
                    text=(temp_path/'server.log').read_text(encoding='utf-8',errors='replace')
                    matches=re.findall(r'offloaded (\d+)/(\d+) layers to GPU',text)
                    if not matches or matches[-1][0]!=matches[-1][1]:
                        raise RuntimeError('Chargement integral sur la carte reservee non confirme')
                return
            except urllib.error.URLError as error:
                if isinstance(error.reason, PermissionError):
                    raise RuntimeError('Connexion locale interdite par l environnement de lancement') from error
                time.sleep(0.5)
            except TimeoutError:
                time.sleep(0.5)
        raise RuntimeError('Le moteur ne devient pas disponible en 180 secondes')

    def ask(self, messages, response_schema=None):
        from observation import span
        with self.inference_lock, span(self, 'model'):
            return self._ask(messages, response_schema)

    def ask_background(self, messages, schema):
        if not self.inference_lock.acquire(blocking=False): return None
        try: return self._ask(messages, schema, max_tokens=256)
        finally: self.inference_lock.release()

    def ask_dialogue(self, messages, response_schema=None):
        """Natural conversation can sample while the JSON grammar stays enforced."""
        from observation import span
        with self.inference_lock, span(self, 'model'):
            return self._ask(messages,response_schema,dialogue=True)

    def ask_memory(self, messages, response_schema=None):
        """Final source recall uses the same native Gemma mode as dialogue."""
        from observation import span
        with self.inference_lock, span(self, 'model'):
            return self._ask(messages,response_schema)

    def count_tokens(self, messages):
        count = self.request('/apply-template', {'messages': messages,
            'chat_template_kwargs':template_settings(self.model_spec)})
        tokens = self.request('/tokenize', {'content': count['prompt'], 'add_special': True})['tokens']
        return len(tokens)

    def count_memory_tokens(self, messages):
        return self.count_tokens(messages)

    def response_messages(self,messages,schema):
        exposed=bool(messages and messages[0].get('role')=='system' and PREFIX in messages[0].get('content',''))
        return with_response_format(messages,schema) if self.model_spec.get('expose_schema') and schema and not exposed else messages

    def count_response_tokens(self,messages,schema):
        return self.count_tokens(self.response_messages(messages,schema))

    def _ask(self, messages, response_schema=None, max_tokens=2048, dialogue=False):
        from observation import emit
        spec=self.model_spec
        messages=self.response_messages(messages,response_schema)
        count = self.count_tokens(messages)
        emit(self,'model.input',{'tokens':count,'structured':response_schema is not None})
        if count > 5500:
            raise RuntimeError('Conversation trop longue : tape /nouveau pour repartir')
        start = time.monotonic()
        payload = {
            'messages': messages, 'temperature': 0.5, 'top_p': 0.95,
            'max_tokens': max_tokens,
            'chat_template_kwargs': template_settings(spec)}
        if response_schema is not None:
            payload['response_format'] = {'type': 'json_object', 'schema': response_schema}
            payload['temperature'] = 0.7 if dialogue else 0
        result = self.request('/v1/chat/completions', payload)
        choice = result['choices'][0]
        content = choice['message'].get('content') or ''
        emit(self,'model.output',{'seconds':time.monotonic()-start,'characters':len(content),
            'finish':choice.get('finish_reason'), 'completion_tokens':result.get('usage',{}).get('completion_tokens')})
        if choice.get('finish_reason') != 'stop' or not content.strip():
            raise RuntimeError('Reponse incomplete : elle ne sera pas ajoutee a la conversation')
        return content, round(time.monotonic() - start, 2), result.get('usage', {})

    def close(self):
        self.done.set()
        self.stop_owned()
        if self.voice:
            self.voice.close()
        if self.thread:
            self.thread.join(timeout=12)
        if self.job:
            self.job.close()
        if self.frame_guard:
            self.frame_guard.close()
        if self.log:
            self.log.close()
        if self.temp:
            # Job termination is asynchronous for children of launcher executables.
            for attempt in range(20):
                try:
                    self.temp.cleanup()
                    break
                except OSError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)

    def stop_owned(self):
        with self.stop_lock:
            self._stop_owned_locked()

    def _stop_owned_locked(self):
        children = list(self.children.values())
        if self.process and self.process not in children:
            children.append(self.process)
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            if child.poll() is None:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


def safety_test():
    job = Job()
    child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        job.assign(child)
        job.close()
        child.wait(timeout=5)
        assert child.poll() is not None
        names = processes()
        assert 'python.exe' in names
        ram = free_ram()
        assert 0 < ram < 128 * 1024**3
        from unittest.mock import patch
        for value in (0, OSError('instrument unavailable')):
            session = Session()
            session.process = subprocess.Popen(
                [sys.executable, '-c', 'import time;time.sleep(60)'],
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                kwargs = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
                with patch(__name__ + '.free_ram', **kwargs):
                    session.watch()
                session.process.wait(timeout=5)
                assert session.reason and session.process.poll() is not None
            finally:
                session.close()
        session = Session()
        session.process = subprocess.Popen(
            [sys.executable, '-c', 'import time;time.sleep(60)'],
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with patch(__name__ + '.processes', return_value={'tftclient-win64-shipping.exe'}):
                session.watch()
            session.process.wait(timeout=5)
            assert session.reason and 'jeu' in session.reason
        finally:
            session.close()
        result = {'job_kill_verified': True, 'low_ram_stop_verified': True,
                  'game_detection_stop_verified': True,
                  'failed_measurement_stop_verified': True, 'process_instrument_sees_python': True,
                  'desktop_witness_visible': 'explorer.exe' in names,
                  'free_ram': ram, 'device': select_device(),
                  'known_games': sorted(GAMES & names)}
        (ROOT / 'config/validation_safety.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    finally:
        job.close()
        if child.poll() is None:
            child.kill()
            child.wait()


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--safety-test', action='store_true')
    parser.add_argument('--voice', action='store_true')
    parser.add_argument('--codex', action='store_true')
    parser.add_argument('--allow-game', action='store_true')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if args.safety_test:
        print(json.dumps(safety_test(), indent=2))
        return
    session = Session(allow_game=args.allow_game, context_window=16384 if args.codex else 8192)
    report = {'status': 'started', 'rows': [], 'real_memory_opened': False}
    try:
        print('Chargement du modele local. Aucun souvenir personnel.', flush=True)
        session.start()
        messages = [{'role': 'system', 'content': SYSTEM}]
        if args.codex:
            messages[0]['content'] += (' Une fonction separee est disponible : si l utilisateur tape '
                '/faire suivi de sa demande, Codex utilise ce meme modele pour travailler dans '
                'laboratoire/atelier. Dans le dialogue ordinaire, tu n executes pas d action. '
                'Explique cette commande si on te demande de creer ou modifier un fichier. '
                'Tu ne vois pas les resultats des taches precedentes et ne dois pas les inventer.')
        if args.voice:
            from voice_link import Voice
            messages[0]['content'] += (' Tes reponses seront lues par une voix synthetique. '
                'Reponds en une ou deux phrases courtes, sans Markdown ni liste, au plus 60 mots.')
            print('Chargement de la voix d Alice...', flush=True)
            session.voice = Voice(session)
            session.voice.start()
            report['voice_ready'] = session.voice.ready
        if args.smoke:
            trials = [
                'Bonjour. Explique en deux phrases ce que tu peux faire dans ce laboratoire.',
                'Le dossier fictif validation_demo contient 3 fichiers de 12 Mo. Quelle est leur taille totale ?',
                'Lina propose de remplacer Marc demain. Marc n a pas encore accepte. Qui est actuellement responsable ?',
                'Ouvre mes documents et dis-moi ce que tu y trouves.']
            for prompt in trials:
                text, elapsed, usage = session.ask([messages[0], {'role': 'user', 'content': prompt}])
                report['rows'].append({'prompt': prompt, 'answer': text, 'seconds': elapsed, 'usage': usage})
                if args.voice:
                    import shutil
                    path, audio = session.voice.synthesize(text)
                    audio.pop('file', None)
                    report['rows'][-1]['voice'] = audio
                    report['rows'][-1]['reply_to_audio_seconds'] = round(elapsed + audio['synthesis_seconds'], 3)
                    if len(report['rows']) == 1:
                        (ROOT / 'outputs').mkdir(exist_ok=True)
                        shutil.copyfile(path, ROOT / 'outputs/exemple_gpt_oss.wav')
                    path.unlink()
                print(json.dumps(report['rows'][-1], ensure_ascii=False), flush=True)
            report['status'] = 'responses_captured_pending_review'
        else:
            print('Pret. /nouveau : effacer la conversation ; /quitter : arreter.\n')
            if args.codex:
                print('/faire suivi de ta demande : travail technique dans laboratoire/atelier.\n')
            while True:
                session.check()
                prompt = input('Toi > ').strip()
                if prompt.lower() == '/quitter':
                    break
                if prompt.lower() == '/nouveau':
                    messages = messages[:1]
                    print('Conversation effacee.')
                    continue
                if not prompt:
                    continue
                if args.codex and (prompt == '/faire' or prompt.startswith('/faire ')):
                    from codex_link import run_task, action_reply
                    task = prompt[len('/faire'):].strip()
                    if not task:
                        print('Exemple : /faire Cree une page HTML qui affiche Bonjour Proprietaire.')
                        continue
                    result = run_task(session, task)
                    print('\nCompte rendu du modele local (a verifier) :\n' + result['answer'])
                    print('Fichiers modifies dans l atelier :', ', '.join(result['changed_files']) or 'aucun')
                    text = action_reply(result)
                    print(text)
                    if session.voice:
                        session.voice.speak(text)
                    continue
                trial = messages + [{'role': 'user', 'content': prompt}]
                try:
                    text, elapsed, _ = session.ask(trial)
                except (RuntimeError, urllib.error.URLError) as error:
                    session.check()
                    print('Demande non terminee :', error)
                    continue
                messages = trial + [{'role': 'assistant', 'content': text}]
                print(f'\nAlice > {text}\n[{elapsed} s]\n')
                if session.voice:
                    session.voice.speak(text)
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        if session.temp:
            path = Path(session.temp.name) / 'server.log'
            if path.exists():
                # No user conversations are persisted by interactive mode.
                if args.smoke:
                    report['diagnostic_tail'] = path.read_text(encoding='utf-8', errors='replace')[-6000:]
        raise
    finally:
        if args.smoke and session.temp:
            path = Path(session.temp.name) / 'server.log'
            if path.exists():
                report['backend_evidence'] = [line for line in path.read_text(
                    encoding='utf-8', errors='replace').splitlines() if any(
                    word in line.lower() for word in ('buffer', 'offload', 'vulkan', 'load_mode', 'load mode'))]
            voice_log = Path(session.temp.name) / 'voice.log'
            if voice_log.exists() and report['status'] == 'failed':
                report['voice_diagnostic_tail'] = voice_log.read_text(encoding='utf-8', errors='replace')[-5000:]
        session.close()
        if args.smoke:
            report['minimum_free_ram_bytes'] = session.minimum_ram
            report['guard_reason'] = session.reason
            if session.frame_guard:
                report['fps_guard_report'] = session.frame_guard.path.as_posix()
            report['device'] = getattr(session, 'device', None)
            report['server_stopped'] = session.process is None or session.process.poll() is not None
            report['temporary_data_removed'] = session.temp is None or not Path(session.temp.name).exists()
            report['audio_played'] = False
            report['microphone_opened'] = False
            (ROOT / ('config/validation_voice_smoke.json' if args.voice else 'config/validation_smoke.json')).write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nSession arretee.')
    except Exception as error:
        print('ERREUR :', error)
        sys.exit(1)
