"""Launch Slay the Spire from an already running Alice desktop session."""
from pathlib import Path
import os
import secrets
import subprocess
import tempfile
import threading


class DesktopGameLauncher:
    def __init__(self, app, root):
        self.app = app
        self.root = Path(root)
        self.lock = threading.Lock()
        self.launching = False
        self.process = None

    def launch(self):
        """Return immediately to Tk; the game and its console run off-thread."""
        with self.lock:
            if self.launching or self.app.stop.is_set():
                return False
            self.launching = True
        self.app.events.put(('game_button', ('Lancement en cours...', 'disabled')))
        threading.Thread(target=self._run, name='alice-sts-launch', daemon=True).start()
        return True

    def _ensure_bridge(self):
        if self.app.stop.is_set():
            raise RuntimeError('Alice est en cours d arret.')
        if self.app.session is None or self.app.game_context is None:
            raise RuntimeError('Alice termine encore son chargement. Reessaie dans un instant.')
        if self.app.game_bridge is None:
            from game_stream_bridge import GameBridge
            bridge = GameBridge(
                self.app.session, self.app.game_context,
                self.root / 'data/slay_spire/bridge/current.json',
                secrets.token_hex(32),
                on_notice=lambda event: self.app.events.put(('text',
                    ('Alice joue', event['action'] +
                     (' : ' + event['reason'] if event['reason'] else '')))))
            bridge.start()
            if self.app.stop.is_set():
                bridge.close()
                raise RuntimeError('Alice est en cours d arret.')
            self.app.game_bridge = bridge
        return self.app.game_bridge

    def _run(self):
        try:
            bridge = self._ensure_bridge()
            script = self.root / 'jeux/slay_spire/lancer.ps1'
            if not script.is_file():
                raise FileNotFoundError('Lanceur Slay the Spire introuvable.')
            env = os.environ.copy()
            env['ALICE_STS_BRIDGE_FILE'] = str(bridge.state_file)
            env['ALICE_STS_BRIDGE_TOKEN'] = bridge.token
            if self.app.stop.is_set():
                raise RuntimeError('Alice est en cours d arret.')
            command = ['powershell.exe', '-NoProfile', '-NonInteractive',
                       '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Mode', 'alice']
            with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as errors:
                self.process = subprocess.Popen(
                    command, cwd=script.parent, env=env,
                    stdout=subprocess.DEVNULL, stderr=errors,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                self.app.events.put(('game_button', ('Jeu en cours', 'disabled')))
                code = self.process.wait()
                if code:
                    errors.seek(0)
                    detail = errors.read()[-1200:].strip()
                    raise RuntimeError(detail or f'Le lanceur a quitte avec le code {code}.')
            self.app.events.put(('text', ('Slay the Spire',
                'Jeu ferme. Alice reste ouverte et tu peux lancer une autre partie.')))
        except Exception as error:
            self.app.events.put(('text', ('Slay the Spire',
                'Lancement non termine : ' + str(error)[:1200])))
        finally:
            with self.lock:
                self.process = None
                self.launching = False
            self.app.events.put(('game_button', ('Jouer à Slay the Spire', 'normal')))
