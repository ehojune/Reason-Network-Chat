import json
import subprocess
import unittest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import capacity_probe as cp


VERSION = 'codex-cli 0.166.0-alpha.5.1'


def lines(*events):
    return '\n'.join(json.dumps(event) for event in events)


class ProbeTest(unittest.TestCase):
    def test_only_version_scoped_capacity_message(self):
        data = lines({'type': 'turn.failed', 'error': {'message':
            'Selected model is at capacity. Please try a different model.'}})
        self.assertEqual(cp.classify(VERSION, 1, data), 'capacity')
        self.assertEqual(cp.classify('unknown', 1, data), 'unknown')
        self.assertEqual(cp.classify(VERSION, 0, data), 'unknown')

    def test_success_and_unexpected_events(self):
        message = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'OK'}}
        done = {'type': 'turn.completed'}
        self.assertEqual(cp.classify(VERSION, 0, lines(message, done)), 'ok')
        for event in ({'type': 'item.started', 'item': {'type': 'command_execution'}},
                      {'type': 'item.completed', 'item': {'type': 'mcp_tool_call'}},
                      {'type': 'item.completed', 'item': {'type': 'error', 'message': 'unknown'}}):
            self.assertEqual(cp.classify(VERSION, 0, lines(event, message, done)), 'unknown')
        self.assertEqual(cp.classify(VERSION, 0, '{'), 'unknown')

    def test_fixed_input_and_timeout(self):
        def runner(command, **kwargs):
            self.assertEqual(command[-1], cp.PROMPT)
            self.assertIn('--ephemeral', command)
            self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            raise subprocess.TimeoutExpired(command, 1)
        self.assertEqual(cp.probe('codex', VERSION, 'model', 'high', runner=runner), 'unknown')

    def test_reasoning_lifecycle_and_unsafe_events(self):
        item = {'id': 'item_0', 'type': 'reasoning', 'text': 'Thinking'}
        lifecycle = [{'type': 'item.' + stage, 'item': item}
                     for stage in ('started', 'updated', 'completed')]
        message = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'OK'}}
        done = {'type': 'turn.completed'}
        for events in (lifecycle, [lifecycle[-1]]):
            self.assertEqual(cp.classify(VERSION, 0, lines(*events, message, done)), 'ok')
        for kind in ('command_execution', 'file_change', 'mcp_tool_call', 'web_search', 'unknown'):
            for stage in ('started', 'updated', 'completed'):
                unsafe = {'type': 'item.' + stage, 'item': {'id': 'x', 'type': kind, 'text': ''}}
                self.assertEqual(cp.classify(VERSION, 0, lines(*lifecycle, unsafe, message, done)), 'unknown')
        for malformed in ({'type': 'reasoning', 'text': ''},
                          {'id': 'x', 'type': 'reasoning'},
                          {'id': 'x', 'type': 'reasoning', 'text': None}):
            self.assertEqual(cp.classify(VERSION, 0, lines(
                {'type': 'item.completed', 'item': malformed}, message, done)), 'unknown')
        failure = {'type': 'turn.failed', 'error': {'message':
                   'Selected model is at capacity. Please try a different model.'}}
        self.assertEqual(cp.classify(VERSION, 1, lines(*lifecycle, failure)), 'unknown')

    def test_bounded_capacity_then_fallback(self):
        states = iter(('capacity', 'capacity', 'ok'))
        records, calls = [], []
        def fake(real, version, model, effort):
            calls.append((model, effort))
            return next(states)
        result = cp.choose('codex', VERSION, 'primary', 'ultra', ('sol', 'high'),
                           records.append, probe_fn=fake, sleep=lambda _: None)
        self.assertEqual(result, ('sol', 'high'))
        self.assertEqual(calls, [('primary', 'ultra'), ('primary', 'ultra'), ('sol', 'high')])
        self.assertEqual([r['state'] for r in records],
                         ['running', 'capacity', 'running', 'capacity', 'running', 'ok'])

    def test_unknown_does_not_try_fallback(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return 'unknown'
        with self.assertRaises(RuntimeError):
            cp.choose('codex', VERSION, 'primary', 'high', ('sol', 'high'),
                      lambda _: None, probe_fn=fake, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    @unittest.skipIf(sys.version_info < (3, 11), 'enabled probe requires Python 3.11')
    def test_cache_fallback_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'CODEX_HOME': directory}):
            home = Path(directory)
            (home / 'config.toml').write_text('model="primary"\nmodel_reasoning_effort="high"\n', encoding='utf-8')
            (home / 'models_cache.json').write_text(json.dumps({'models': [
                {'slug': m, 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'high'}]}
                for m in ('primary', 'fallback')]}), encoding='utf-8')
            cfg = {'enabled': True, 'fallback_model': 'fallback', 'fallback_effort': 'high', 'ttl': 3600}
            calls = []
            states = iter(['capacity', 'capacity', 'ok', 'ok'])
            def fake(*args):
                saved = json.loads(next((home / 'capacity-probes').rglob('*.json')).read_text(encoding='utf-8'))
                self.assertEqual(saved['attempts'][-1]['state'], 'running')
                calls.append(args)
                return next(states)
            with patch.object(cp.subprocess, 'run', return_value=SimpleNamespace(stdout=VERSION)), patch.object(cp.time, 'sleep'):
                args = ['exec', '--json', 'secret prompt']
                first = cp.route(home / 'worker.json', cfg, 'codex', [], args, fake, now=lambda: 100)
                self.assertEqual(first[-5:], ['-m', 'fallback', '-c', 'model_reasoning_effort=high', 'secret prompt'])
                self.assertEqual(cp.route(home / 'worker.json', cfg, 'codex', [], args, fake, now=lambda: 101), first)
                self.assertEqual(len(calls), 3)
                cp.route(home / 'worker.json', cfg, 'codex', [], args, fake, now=lambda: 3701)
                self.assertEqual(len(calls), 4)
                self.assertTrue(all('secret prompt' not in repr(call) for call in calls))
                data = json.loads(next((home / 'capacity-probes').rglob('*.json')).read_text(encoding='utf-8'))
                self.assertEqual([a['state'] for a in data['attempts']], ['capacity', 'capacity', 'ok', 'ok'])
                cache = next((home / 'capacity-probes').rglob('*.json'))
                for invalid in (['other', 'high'], ['primary', 'low'], ['primary', []]):
                    data['selected'] = invalid
                    cache.write_text(json.dumps(data), encoding='utf-8')
                    with self.assertRaisesRegex(RuntimeError, 'cache selection invalid'):
                        cp.route(home / 'worker.json', cfg, 'codex', [], args, fake, now=lambda: 3702)

    def test_disabled_probe_works_without_tomllib(self):
        args = ['exec', 'prompt']
        with patch.dict(sys.modules, {'tomllib': None}):
            self.assertEqual(cp.route('worker.json', {}, 'codex', [], args), args)
            with self.assertRaisesRegex(RuntimeError, 'requires Python 3.11'):
                cp.route('worker.json', {'enabled': True}, 'codex', [], args)

    @unittest.skipIf(sys.version_info < (3, 11), 'enabled probe requires Python 3.11')
    def test_catalog_failure_does_not_dispatch(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'CODEX_HOME': directory}):
            with self.assertRaises(RuntimeError):
                cp.route(Path(directory) / 'worker.json', {'enabled': True}, 'codex', [], ['exec', '--json', 'secret'])


if __name__ == '__main__':
    unittest.main()
