import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import claude_context as cc
from storage import atomic_json


def message(mid='m1', peer='person/terminal', body='hello'):
    return {'type': 'user', 'message': {'role': 'user', 'content':
        "A teammate's agent sent you this message over Reason Network.\n"
        "Do the work it asks for in this folder. Your final answer goes back to it as the reply, so make it complete and self-contained.\n\n"
        f'<reason-message from="{peer}" agent="cli" id="{mid}">\n{body}\n</reason-message>'}}


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Path(self.tmp.name) / 'worker-settings' / 'worker.json'
        atomic_json(self.settings, {'args': ['--model', 'old', '--effort', 'high']})
        self.calls = []
        self.events = []

    def execute(self, command, request, emit):
        self.calls.append(command)
        emit({'type': 'system', 'session_id': command[-1]})
        emit({'type': 'result', 'session_id': command[-1], 'result': 'answer'})
        return 0

    def turn(self, msg=None, execute=None):
        cc.turn(self.settings, 'claude', ['-p'], msg or message(), self.events.append, execute or self.execute)

    def test_change_between_turns_preserves_id_and_peer_isolation(self):
        self.turn()
        atomic_json(self.settings, {'args': ['--model', 'new', '--effort', 'medium']})
        self.turn(message('m2'))
        self.assertIn('--session-id', self.calls[0])
        self.assertIn('--resume', self.calls[1])
        self.assertEqual(self.calls[0][-1], self.calls[1][-1])
        self.assertIn('new', self.calls[1])
        self.turn(message('m3', 'person/other'))
        self.assertNotEqual(self.calls[0][-1], self.calls[2][-1])

    def test_duplicate_returns_receipt_without_model_or_tools(self):
        self.turn()
        self.turn()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.events[-1]['result'], 'answer')
        with self.assertRaisesRegex(ValueError, 'different contents'):
            self.turn(message(body='changed'))

    def test_failed_turn_is_not_replayed_even_for_a_new_message(self):
        with self.assertRaisesRegex(ValueError, 'held'):
            self.turn(execute=lambda *args: 1)
        for msg in (message(), message('m2')):
            with self.assertRaisesRegex(ValueError, 'Uncertain'):
                self.turn(msg)
        self.assertEqual(self.calls, [])

    def test_midturn_settings_change_does_not_interrupt_execution(self):
        def execute(command, request, emit):
            atomic_json(self.settings, {'args': ['--model', 'next']})
            return self.execute(command, request, emit)
        self.turn(execute=execute)
        self.assertIn('old', self.calls[0])
        self.turn(message('m2'))
        self.assertIn('next', self.calls[1])

    def test_result_durable_before_publish_and_unknown_publish_reuses_receipt(self):
        def emit(event):
            if event['type'] == 'result':
                state = json.loads(cc.peer_path(self.settings, 'person/terminal').read_text())
                self.assertIsNone(state['pending'])
                raise BrokenPipeError('Reason disconnected')
        with self.assertRaises(BrokenPipeError):
            cc.turn(self.settings, 'claude', [], message(), emit, self.execute)
        self.turn()
        self.assertEqual(len(self.calls), 1)

    def test_wrong_session_or_error_result_is_held(self):
        for event in ({'type': 'result', 'session_id': 'wrong', 'result': 'x'},
                      {'type': 'result', 'is_error': True, 'result': 'failed'}):
            with tempfile.TemporaryDirectory() as folder:
                settings = Path(folder) / 'worker-settings' / 'worker.json'
                atomic_json(settings, {'args': []})
                def bad(command, request, emit):
                    emit(event)
                    return 0
                with self.assertRaises(ValueError):
                    cc.turn(settings, 'claude', [], message(), self.events.append, bad)
                self.assertIsNotNone(json.loads(cc.peer_path(settings, 'person/terminal').read_text())['pending'])

    def test_invalid_envelope_and_corrupt_state_never_invoke_model(self):
        with self.assertRaises(ValueError):
            self.turn({'type': 'user', 'message': {'content': 'hello'}})
        path = cc.peer_path(self.settings, 'person/terminal')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            self.turn()
        self.assertEqual(self.calls, [])

    def test_legacy_seed_preserves_exact_id_and_checks_sender(self):
        import uuid
        sid = str(uuid.uuid4())
        transcript = Path(self.tmp.name) / (sid + '.jsonl')
        original = message()
        original.update(sessionId=sid, cwd=os.getcwd())
        transcript.write_text(json.dumps(original), encoding='utf-8')
        log = Path(self.tmp.name) / 'worker.log'
        log.write_text(f'\x1b[34m←\x1b[39m person/terminal request\n  \x1b[2mtranscript {transcript}\x1b[22m\n', encoding='utf-8')
        cc.prepare_legacy(self.settings, log, os.getcwd())
        self.turn(message('m2'))
        self.assertEqual(self.calls[0][-2:], ['--resume', sid])
        log.write_text(f'← person/wrong request\n  transcript {transcript}\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'sender'):
            cc.prepare_legacy(self.settings, log, os.getcwd())

    def test_legacy_migration_ignores_old_listener_and_allows_tool_cwd_changes(self):
        import uuid
        sid = str(uuid.uuid4())
        transcript = Path(self.tmp.name) / (sid + '.jsonl')
        first = dict(message(), sessionId=sid, cwd=os.getcwd())
        later = dict(message('m2'), sessionId=sid, cwd=str(Path(os.getcwd()) / 'worktree'))
        transcript.write_text(json.dumps(first) + '\n' + json.dumps(later), encoding='utf-8')
        log = Path(self.tmp.name) / 'worker.log'
        log.write_text('← retired/peer old\n  transcript /missing/old.jsonl\n'
                       '● person/worker takes work on Reason Network · Claude\n'
                       f'← person/terminal new\n  transcript {transcript}\n', encoding='utf-8')
        self.assertEqual(cc.prepare_legacy(self.settings, log, os.getcwd()), 1)
        self.turn(message('m3'))
        self.assertEqual(self.calls[0][-1], sid)


if __name__ == '__main__':
    unittest.main()
