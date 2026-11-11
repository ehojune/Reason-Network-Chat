import contextlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import registration_recovery as rr


class RecoveryTests(unittest.TestCase):
    def test_only_repeated_unsuperseded_registration_errors_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'worker.log'
            p.write_text(rr.ERROR+'\n'+rr.ERROR, encoding='utf-8')
            self.assertTrue(rr.registration_error(p))
            p.write_text('\x1b[2m'+rr.ERROR+'\x1b[22m\n'+rr.ERROR,encoding='utf-8')
            self.assertTrue(rr.registration_error(p))
            for suffix in ('\n→ peer 1s · OK', '\n● owner/name takes work on Reason Network · Claude'):
                p.write_text(rr.ERROR+'\n'+rr.ERROR+suffix, encoding='utf-8')
                self.assertFalse(rr.registration_error(p))

    def test_idle_repair_preserves_model_and_checks_frozen_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = dict(name='test-worker', pid=42, family='claude', claudeContext=True,
                          cwd=directory, model='fable', effort='high', fullAccess=True)
            launcher = Mock(workers={'test-worker':worker}, restarting=set(),
                            lock=threading.Lock(), operation_lock=threading.RLock())
            launcher.alive.return_value = True
            launcher.wait_context_exit.return_value = True
            launcher.start_worker.return_value = dict(worker, pid=43)
            observe = Mock(return_value={'status':'idle', 'pending':[]})
            with patch('launcher.HOME', Path(directory)), patch('launcher.kill_tree') as kill, \
                 patch('claude_context.paused_ingress', return_value=contextlib.nullcontext()):
                rr.repair(launcher, worker, observe)
            self.assertEqual(observe.call_count,2)
            kill.assert_called_once_with(42)
            self.assertEqual(launcher.workers['test-worker']['pid'],43)
            self.assertEqual(launcher.start_worker.call_args.args[1:],
                             (directory,'fable','high','test-worker',True,None))
            launcher.settle.assert_called_once()

    def test_racing_request_or_unpublished_reply_prevents_kill(self):
        with tempfile.TemporaryDirectory() as directory:
            worker=dict(name='test-worker',pid=42,family='codex')
            launcher=Mock(workers={'test-worker':worker},restarting=set(),lock=threading.Lock(),
                          operation_lock=threading.RLock())
            for outbox in (False,True):
                observe=Mock(side_effect=[{'status':'idle','pending':[]}, {'status':'idle','pending':['new']}])
                if outbox:
                    p=Path(directory)/'.reason/ask-workers/test-worker.json'
                    p.parent.mkdir(parents=True)
                    p.write_text(json.dumps([{'request':{'id':'done'},'reply':'cached'}]))
                with patch('launcher.HOME',Path(directory)), patch('launcher.kill_tree') as kill, \
                     patch('claude_context.paused_ingress',return_value=contextlib.nullcontext()):
                    with self.assertRaises(ValueError):
                        rr.repair(launcher,worker,observe)
                    kill.assert_not_called()
                    launcher.start_worker.assert_not_called()
