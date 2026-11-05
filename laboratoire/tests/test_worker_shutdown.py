import sys
from pathlib import Path
import unittest
import threading
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from voice_link import Voice
from hearing_link import Hearing


class InterruptedWorker(unittest.TestCase):
    def test_dead_worker_broken_input_does_not_prevent_log_cleanup(self):
        worker = Voice(Mock())
        worker.process = Mock()
        worker.process.poll.return_value = 1
        worker.process.stdin.close.side_effect = OSError(22, 'Broken pipe')
        worker.log = Mock()
        worker.close()
        worker.process.stdout.close.assert_called_once()
        worker.log.close.assert_called_once()

    def test_guard_failure_prevents_hearing_pipe_write(self):
        session = Mock()
        session.check.side_effect = RuntimeError('FPS unavailable')
        worker = Hearing(session)
        worker.process = Mock()
        with self.assertRaisesRegex(RuntimeError, 'FPS unavailable'):
            worker.command('listen')
        worker.process.stdin.write.assert_not_called()

    def test_pause_before_listen_never_opens_microphone(self):
        worker = Hearing(Mock())
        worker.process = Mock()
        worker.process.poll.return_value = None
        worker.write_lock = threading.Lock()
        self.assertEqual(worker.command('listen', cancel_if=lambda: True)['status'], 'idle')
        worker.process.stdin.write.assert_not_called()

    def test_pending_public_message_cancels_capture_once_and_drains_reply(self):
        worker=Hearing(Mock())
        worker.process=Mock()
        worker.process.poll.return_value=None
        worker.write_lock=threading.Lock()
        condition=Mock(side_effect=[False,True])
        def receive(timeout,on_poll=None):
            on_poll();on_poll()
            return {'id':1,'status':'idle'}
        worker.receive=receive
        self.assertEqual(worker.command('listen',cancel_if=condition)['status'],'idle')
        self.assertEqual(worker.process.stdin.write.call_count,2)
        self.assertEqual(worker.sequence,1)
        self.assertEqual(condition.call_count,2)

    def test_public_ready_requests_idle_yield_instead_of_cancelling_human_speech(self):
        worker=Hearing(Mock());worker.process=Mock()
        worker.process.poll.return_value=None;worker.write_lock=threading.Lock()
        def receive(timeout,on_poll=None):
            on_poll();on_poll()
            return {'id':1,'status':'transcribed','accepted':True,'cleaned':'validation parole prioritaire'}
        worker.receive=receive
        result=worker.command('listen',cancel_if=lambda:False,yield_if=lambda:True)
        writes=[call.args[0] for call in worker.process.stdin.write.call_args_list]
        self.assertEqual(len(writes),2)
        self.assertIn('yield_if_idle',writes[1])
        self.assertNotIn('cancel',writes[1])
        self.assertEqual(result['status'],'transcribed')


if __name__ == '__main__':
    unittest.main()
