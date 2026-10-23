"""The backend and recipient preview consume the same routing examples."""
import json
from pathlib import Path
import unittest

import relay


class RoutingTest(unittest.TestCase):
    def test_markdown_mentions_are_not_recipients(self):
        cases = json.loads(Path(__file__).with_name('routing_cases.json').read_text(encoding='utf-8'))
        room = {'members': ['p/a', 'p/b', 'p/c']}
        for case in cases:
            with self.subTest(text=case['text']):
                self.assertEqual(relay.Relay.mentioned(room, case['text']), case['to'])
                self.assertEqual(relay.Relay.targets(room, case['text']), case['to'])

    def test_many_unmatched_code_delimiters_do_not_lose_a_real_mention(self):
        text = ' '.join('`' * n for n in range(1, 300)) + '\n@a'
        self.assertEqual(relay.Relay.mentioned({'members': ['p/a']}, text), ['p/a'])
