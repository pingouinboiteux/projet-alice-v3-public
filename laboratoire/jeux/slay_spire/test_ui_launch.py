"""The desktop game button reuses Alice without starting a second model."""
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import sys


LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / 'scripts'))
from desktop_game import DesktopGameLauncher
from desktop_commands import poll


class DesktopGameLaunchTests(unittest.TestCase):
    def test_button_starts_existing_session_bridge_and_game_lifecycle(self):
        calls = []

        class Bridge:
            def __init__(self, session, context, state_file, token, **kwargs):
                self.session = session
                self.context = context
                self.state_file = state_file
                self.token = token
                self.started = False

            def start(self):
                self.started = True

        class Process:
            def wait(self):
                return 0

        def launch_process(command, **kwargs):
            calls.append((command, kwargs))
            return Process()

        with tempfile.TemporaryDirectory(prefix='validation_sts_ui_',
                                         dir=LAB / 'data/validation') as directory:
            root = Path(directory)
            script = root / 'jeux/slay_spire/lancer.ps1'
            script.parent.mkdir(parents=True)
            script.touch()
            session = object()
            context = object()
            app = SimpleNamespace(stop=threading.Event(), session=session,
                                  game_context=context, game_bridge=None,
                                  events=Queue())
            game = DesktopGameLauncher(app, root)
            with patch('game_stream_bridge.GameBridge', Bridge), \
                 patch('desktop_game.subprocess.Popen', launch_process):
                game._run()
            self.assertTrue(app.game_bridge.started)
            self.assertIs(app.game_bridge.session, session)
            self.assertIs(app.game_bridge.context, context)
            self.assertEqual(len(calls), 1)
            command, options = calls[0]
            self.assertEqual(command[-2:], ['-Mode', 'alice'])
            self.assertEqual(options['env']['ALICE_STS_BRIDGE_TOKEN'],
                             app.game_bridge.token)
            self.assertEqual(options['env']['ALICE_STS_BRIDGE_FILE'],
                             str(app.game_bridge.state_file))
            self.assertFalse(game.launching)
            self.assertEqual(app.events.get_nowait()[0], 'game_button')
            self.assertEqual(app.events.get_nowait()[0], 'text')
            self.assertEqual(app.events.get_nowait(),
                             ('game_button', ('Jouer à Slay the Spire', 'normal')))

    def test_shutdown_refuses_game_launch(self):
        app = SimpleNamespace(stop=threading.Event(), session=object(),
                              game_context=object(), game_bridge=None,
                              events=Queue())
        app.stop.set()
        game = DesktopGameLauncher(app, LAB)
        self.assertFalse(game.launch())
        self.assertTrue(app.events.empty())

    def test_second_click_cannot_launch_a_second_game(self):
        entered = threading.Event()
        release = threading.Event()
        starts = []

        class Process:
            def wait(self):
                entered.set()
                release.wait(3)
                return 0

        def launch_process(*args, **kwargs):
            starts.append(args)
            return Process()

        with tempfile.TemporaryDirectory(prefix='validation_sts_ui_',
                                         dir=LAB / 'data/validation') as directory:
            root = Path(directory)
            script = root / 'jeux/slay_spire/lancer.ps1'
            script.parent.mkdir(parents=True)
            script.touch()
            bridge = SimpleNamespace(state_file=root / 'bridge.json', token='a' * 64)
            app = SimpleNamespace(stop=threading.Event(), session=object(),
                                  game_context=object(), game_bridge=bridge,
                                  events=Queue())
            game = DesktopGameLauncher(app, root)
            with patch('desktop_game.subprocess.Popen', launch_process):
                self.assertTrue(game.launch())
                self.assertTrue(entered.wait(3))
                self.assertFalse(game.launch())
                self.assertEqual(len(starts), 1)
                release.set()
                while True:
                    item = app.events.get(timeout=3)
                    if item == ('game_button', ('Jouer à Slay the Spire', 'normal')):
                        break
            self.assertFalse(game.launching)

    def test_failed_launcher_reports_error_and_restores_button(self):
        class Process:
            def wait(self):
                return 1

        def launch_process(command, **kwargs):
            kwargs['stderr'].write('Slay the Spire est deja ouvert.\n')
            kwargs['stderr'].flush()
            return Process()

        with tempfile.TemporaryDirectory(prefix='validation_sts_ui_',
                                         dir=LAB / 'data/validation') as directory:
            root = Path(directory)
            script = root / 'jeux/slay_spire/lancer.ps1'
            script.parent.mkdir(parents=True)
            script.touch()
            app = SimpleNamespace(stop=threading.Event(), session=object(),
                game_context=object(), game_bridge=SimpleNamespace(
                    state_file=root / 'bridge.json', token='a' * 64), events=Queue())
            game = DesktopGameLauncher(app, root)
            with patch('desktop_game.subprocess.Popen', launch_process):
                game._run()
            self.assertEqual(app.events.get_nowait(),
                             ('game_button', ('Jeu en cours', 'disabled')))
            self.assertIn('deja ouvert', app.events.get_nowait()[1][1])
            self.assertEqual(app.events.get_nowait(),
                             ('game_button', ('Jouer à Slay the Spire', 'normal')))

    def test_desktop_event_updates_button_without_touching_game(self):
        app = SimpleNamespace(
            observation=SimpleNamespace(io_error=None),
            observation_status=Mock(), diagnostic_enabled=Mock(),
            stop=threading.Event(), finished=threading.Event(),
            events=Queue(), game_button=Mock(), window=Mock(), poll=Mock())
        app.diagnostic_enabled.get.return_value = False
        app.events.put(('game_button', ('Jeu en cours', 'disabled')))
        platform = SimpleNamespace(windll=SimpleNamespace(user32=Mock()))
        platform.windll.user32.GetAsyncKeyState.return_value = 0
        poll(app, platform, Mock())
        app.game_button.configure.assert_called_once_with(
            text='Jeu en cours', state='disabled')


if __name__ == '__main__':
    unittest.main()
