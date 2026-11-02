import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import recovery
import launcher


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Path(self.tmp.name) / 'worker-settings' / 'worker.json'
        self.args = ['exec', '--json', '<reason-message from="u" agent="cli" id="a">hello</reason-message>']
        self.path = recovery.journal_path(self.settings)

    def invoke(self, script):
        with contextlib.redirect_stdout(io.StringIO()):
            return recovery.run(self.settings, sys.executable, ['-c', script], self.args)

    def test_success_cached_before_emission_and_never_reexecuted(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'answer'}},
                  {'type': 'turn.completed'}]
        script = 'import json; print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')'
        self.assertEqual(self.invoke(script), 0)
        saved = json.loads(self.path.read_text(encoding='utf-8'))['requests']['a']
        self.assertEqual(saved['status'], 'completed')
        self.assertIn('answer', saved['output'])
        with patch.object(recovery.subprocess, 'Popen', side_effect=AssertionError('reexecuted')):
            with self.assertRaisesRegex(RuntimeError, 'cached result'):
                self.invoke(script)

    def test_interruption_and_restart_are_held(self):
        for event in ({'type': 'item.started', 'item': {'type': 'command_execution'}},
                      {'type': 'item.started', 'item': {'type': 'file_change'}},
                      {'type': 'turn.failed', 'error': {'message': 'capacity'}}):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                self.settings = Path(directory) / 'worker-settings' / 'worker.json'
                script = 'import json; print(json.dumps(' + repr(event) + ')); raise SystemExit(1)'
                with self.assertRaises(RuntimeError):
                    self.invoke(script)
                path = recovery.journal_path(self.settings)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['requests']['a']['status'], 'held')
                with patch.object(recovery.subprocess, 'Popen', side_effect=AssertionError('reexecuted')):
                    with self.assertRaisesRegex(RuntimeError, 'held'):
                        self.invoke(script)
                self.assertFalse(recovery.safe_to_retry([event]))

    def test_running_after_crash_and_changed_original_are_held(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'requests': {'a': {'status': 'running', 'original': self.args[-1]}}}), encoding='utf-8')
        with patch.object(recovery.subprocess, 'Popen', side_effect=AssertionError('reexecuted')):
            with self.assertRaisesRegex(RuntimeError, 'held'):
                self.invoke('')
            self.args[-1] += ' changed'
            with self.assertRaisesRegex(RuntimeError, 'conflicts'):
                self.invoke('')

    def test_ambiguous_envelope_cannot_bypass_journal(self):
        self.args[-1] += self.args[-1]
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
            self.invoke('')

    def test_generated_shim_journals_and_holds_duplicate(self):
        self.settings.parent.mkdir(parents=True)
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'done'}},
                  {'type': 'turn.completed'}]
        script = 'print(' + repr('\n'.join(json.dumps(event) for event in events)) + ')'
        self.settings.write_text(json.dumps({'args': ['-c', script]}), encoding='utf-8')
        shim = Path(self.tmp.name) / 'shim.py'
        shim.write_bytes(launcher.SHIM_MAIN)
        env = dict(os.environ, REASON_CHAT_SHIM_SETTINGS=str(self.settings), REASON_CHAT_SHIM_REAL=sys.executable,
                   PYTHONPATH=str(Path(recovery.__file__).resolve().parent))
        command = [sys.executable, str(shim)] + self.args
        first = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn('done', first.stdout)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['requests']['a']['status'], 'completed')
        again = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('cached result', again.stderr)
        self.assertNotIn('done', again.stdout)
