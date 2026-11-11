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
            launcher = Mock(workers={'test-worker':worker}, records={}, restarting=set(),
                            lock=threading.Lock(), operation_lock=threading.RLock())
            launcher.alive.return_value = True
            launcher.operation.side_effect = contextlib.nullcontext
            launcher.wait_context_exit.return_value = True
            launcher.start_worker.return_value = dict(worker, pid=43)
            observe = Mock(return_value={'status':'idle', 'pending':[]})
            with patch('registration_recovery.preflight'), patch('launcher.HOME', Path(directory)), patch('launcher.kill_tree') as kill, \
                 patch('claude_context.paused_ingress', return_value=contextlib.nullcontext()):
                rr.repair(launcher, worker, observe)
            self.assertEqual(observe.call_count,2)
            kill.assert_called_once_with(42)
            self.assertEqual(launcher.workers['test-worker']['pid'],43)
            self.assertEqual(launcher.start_worker.call_args.args[1:],
                             (directory,'fable','high','test-worker',True,None))
            launcher.settle.assert_called_once()
            launcher.operation.assert_called_once()

            # Discovery may know the live identity but only the durable record knows its model.
            discovered = dict(worker, model=None, effort=None)
            launcher.workers['test-worker'] = discovered
            launcher.records['test-worker'] = dict(worker, model='recorded-model',effort='medium',fast=True)
            with patch('registration_recovery.preflight'), patch('launcher.HOME',Path(directory)), patch('launcher.kill_tree'), \
                 patch('claude_context.paused_ingress',return_value=contextlib.nullcontext()):
                rr.repair(launcher,discovered,observe)
            self.assertEqual(launcher.start_worker.call_args.args[1:],
                             (directory,'recorded-model','medium','test-worker',True,True))

    def test_racing_request_or_unpublished_reply_prevents_kill(self):
        with tempfile.TemporaryDirectory() as directory:
            worker=dict(name='test-worker',pid=42,family='codex',cwd=directory)
            launcher=Mock(workers={'test-worker':worker},records={},restarting=set(),lock=threading.Lock(),
                          operation_lock=threading.RLock())
            launcher.operation.side_effect=contextlib.nullcontext
            for outbox in (False,True):
                observe=Mock(side_effect=[{'status':'idle','pending':[]}, {'status':'idle','pending':['new']}])
                if outbox:
                    p=Path(directory)/'.reason/ask-workers/test-worker.json'
                    p.parent.mkdir(parents=True)
                    p.write_text(json.dumps([{'request':{'id':'done'},'reply':'cached'}]))
                with patch('registration_recovery.preflight'), patch('launcher.HOME',Path(directory)), patch('launcher.kill_tree') as kill, \
                     patch('claude_context.paused_ingress',return_value=contextlib.nullcontext()):
                    with self.assertRaises(ValueError):
                        rr.repair(launcher,worker,observe)
                    kill.assert_not_called()
                    launcher.start_worker.assert_not_called()

    def test_missing_replacement_prerequisites_retain_receiver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root/'runtime.exe'
            exe.touch()
            worker = dict(name='test-worker',pid=42,family='codex',cwd=directory)
            launcher = Mock(workers={'test-worker':worker},records={},restarting=set(),
                            lock=threading.Lock(),reason=str(exe))
            launcher.operation.side_effect = contextlib.nullcontext
            launcher.catalog.family.return_value = {'id':'codex'}
            for cwd, runtime, shim in ((str(root/'missing'),str(exe),True),
                                       (directory,None,True),(directory,str(exe),False)):
                launcher.records['test-worker'] = dict(worker,cwd=cwd)
                with patch('launcher.find_codex',return_value=runtime), \
                     patch('launcher.shim_current',return_value=shim), patch('launcher.STATE',root), \
                     patch('launcher.kill_tree') as kill, patch('claude_context.paused_ingress') as pause:
                    with self.assertRaises(ValueError):
                        rr.repair(launcher,worker,Mock())
                    kill.assert_not_called()
                    pause.assert_not_called()
                    launcher.start_worker.assert_not_called()
