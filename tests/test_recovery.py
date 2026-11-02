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
        self.path = recovery.journal_path(self.settings, 'a')

    def invoke(self, script):
        with contextlib.redirect_stdout(io.StringIO()):
            return recovery.run(self.settings, sys.executable, ['-c', script], self.args)

    def test_success_cached_before_emission_and_never_reexecuted(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'answer'}},
                  {'type': 'turn.completed'}]
        script = 'import json; print(' + repr('\n'.join(json.dumps(e) for e in events)) + ')'
        self.assertEqual(self.invoke(script), 0)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
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
                path = recovery.journal_path(self.settings, 'a')
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['status'], 'held')
                with patch.object(recovery.subprocess, 'Popen', side_effect=AssertionError('reexecuted')):
                    with self.assertRaisesRegex(RuntimeError, 'held'):
                        self.invoke(script)
                self.assertFalse(recovery.safe_to_retry([event]))

    def test_running_after_crash_and_changed_original_are_held(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'id': 'a', 'status': 'running', 'original': self.args[-1]}), encoding='utf-8')
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

    def test_broken_output_is_held_with_cached_answer(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'answer'}},
                  {'type': 'turn.completed'}]
        script = 'print(' + repr('\n'.join(json.dumps(event) for event in events)) + ')'

        class BrokenOutput:
            def write(self, value):
                raise BrokenPipeError('closed')

        with patch.object(recovery.sys, 'stdout', BrokenOutput()):
            with self.assertRaises(BrokenPipeError):
                recovery.run(self.settings, sys.executable, ['-c', script], self.args)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'held')
        self.assertIn('Publication unconfirmed', saved['error'])
        self.assertIn('answer', saved['output'])

    def test_distinct_ids_use_distinct_files(self):
        self.assertNotEqual(recovery.journal_path(self.settings, 'a'), recovery.journal_path(self.settings, 'A'))

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
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['status'], 'completed')
        again = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('cached result', again.stderr)
        self.assertNotIn('done', again.stdout)

    def test_packaged_shim_holds_failed_child_and_never_replays(self):
        self.settings.parent.mkdir(parents=True)
        marker = Path(self.tmp.name) / 'child-runs'
        script = ('from pathlib import Path; import json; '
                  'p=Path(' + repr(str(marker)) + '); '
                  'p.write_text(p.read_text()+"x" if p.exists() else "x"); '
                  'print(json.dumps({"type":"turn.failed","error":{"message":"capacity"}})); '
                  'raise SystemExit(1)')
        self.settings.write_text(json.dumps({'args': ['-c', script]}), encoding='utf-8')
        with patch.object(launcher, 'STATE', Path(self.tmp.name) / 'isolated-state'):
            directory = launcher.shim_dir('codex')
            if not directory:
                self.skipTest('packaged shim unavailable')
            shim = Path(directory) / ('codex.exe' if launcher.WIN else 'codex')
            env = dict(os.environ, REASON_CHAT_SHIM_SETTINGS=str(self.settings),
                       REASON_CHAT_SHIM_REAL=sys.executable)
            first = subprocess.run([str(shim)] + self.args, env=env, capture_output=True, text=True, encoding='utf-8')
            again = subprocess.run([str(shim)] + self.args, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(first.returncode, 0)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(marker.read_text(), 'x')
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'held')
        self.assertEqual(saved['original'], self.args[-1])
        self.assertIn('held', again.stderr.lower())
