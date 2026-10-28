import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import antigravity_worker as aw
import launcher


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for name in ('STATE', 'HOME'):
            patch = mock.patch.object(aw, name, self.root)
            patch.start()
            self.addCleanup(patch.stop)
        db = self.root / 'network.db'
        with sqlite3.connect(str(db)) as conn:
            conn.execute('CREATE TABLE messages(id TEXT,sender TEXT,recipient TEXT,body TEXT,sent_at INTEGER,reply_to TEXT)')
        conn.close()
        patch = mock.patch.object(aw, 'NETWORK_DB', db)
        patch.start()
        self.addCleanup(patch.stop)
        self.command = mock.patch.object(aw, 'checked_run', return_value=json.dumps({'person': 'p'}))
        self.run = self.command.start()
        self.addCleanup(self.command.stop)
        self.worker = aw.Worker('gemini-reviewer', self.root, 'agy', 'reason-network', 'gemini-3.8-flash-low', 'p/repo')
        self.addCleanup(self.worker.journal.db.close)

    def job(self, mid='one', body='hello'):
        value = {'id': mid, 'sender': 'p/terminal', 'recipient': 'p/gemini-reviewer', 'body': body, 'sent_at': int(time.time() * 1000)}
        self.worker.journal.enqueue(value)
        return self.worker.journal.db.execute('SELECT * FROM jobs WHERE id=?', (mid,)).fetchone()

    def test_targets_only_one_pr_and_same_owner(self):
        self.assertEqual(aw.pr_target('@gemini-reviewer PR #12 review', 'p/repo'), ('p/repo', 12))
        self.assertEqual(aw.pr_target('review https://github.com/p/other/pull/3', 'p/repo'), ('p/other', 3))
        self.assertIsNone(aw.pr_target('ordinary question', 'p/repo'))
        with self.assertRaises(aw.RequestError):
            aw.pr_target('PR #12 and PR #13', 'p/repo')
        with self.assertRaises(aw.RequestError):
            aw.pr_target('https://github.com/p/repo/pull/12 and PR #13', 'p/repo')
        with self.assertRaises(aw.RequestError):
            aw.pr_target('https://github.com/somebody/else/pull/1', 'p/repo')

    def test_restart_holds_uncertain_call_and_retains_outbox(self):
        self.job('running')
        self.worker.journal.update('running', status='running')
        self.job('outbox')
        self.worker.journal.update('outbox', status='outbox', response='cached')
        recovered = aw.Journal(self.worker.root / 'journal.sqlite3')
        self.addCleanup(recovered.db.close)
        self.assertEqual(recovered.db.execute("SELECT status FROM jobs WHERE id='running'").fetchone()[0], 'running')
        recovered.recover()
        statuses = dict(recovered.db.execute('SELECT id,status FROM jobs'))
        self.assertEqual(statuses, {'running': 'held', 'outbox': 'outbox'})
        self.assertEqual(recovered.get('paused'), '1')

    def test_model_reuses_exact_conversation_and_rejects_false_success(self):
        self.worker.journal.db.execute('INSERT INTO conversations VALUES (?,?)', ('pr:1', 'kept-id'))
        self.worker.journal.db.commit()
        good = {'status': 'SUCCESS', 'response': 'answer', 'conversation_id': 'kept-id'}
        self.run.return_value = json.dumps({'event': 'result', 'result': good})
        self.assertEqual(self.worker.model_call('next', 'pr:1'), good)
        args = self.run.call_args.args[0]
        self.assertEqual(args[args.index('--conversation') + 1], 'kept-id')
        self.assertNotIn('--continue', args)
        self.worker.model_call('review', 'pr:1', aw.SCHEMA)
        self.assertNotIn('--json-schema', self.run.call_args.args[0])
        self.assertIn('"severity"', json.loads(self.run.call_args.kwargs['input'])['message']['content'])
        for bad in ({**good, 'response': ''}, {**good, 'status': 'ERROR'}, {**good, 'denied_actions': ['read']},
                    {**good, 'conversation_id': ''}, {**good, 'conversation_id': 'wrong-id'}):
            self.run.return_value = json.dumps({'event': 'result', 'result': bad})
            with self.assertRaises(aw.WorkerError):
                self.worker.model_call('next', 'pr:1')

    def test_room_metadata_excludes_old_pr_in_envelope(self):
        message = json.loads(self.job(body='[Group room "dev"]\nEarlier PR #10\n---\nPR #11')['payload'])
        self.assertIsNone(self.worker.request(message))  # do not guess before relay metadata is saved
        (self.root / 'relay.json').write_text(json.dumps({'sent': {'one': {'core': 'PR #11', 'speaker': 'p/lead', 'room': 'r'}}}))
        self.assertEqual(self.worker.request(message), ('PR #11', 'p/lead', 'r'))

    def test_reply_deduplicates_exact_result_but_not_failure_notice(self):
        with sqlite3.connect(str(aw.NETWORK_DB)) as conn:
            conn.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', ('notice', self.worker.address, 'p/terminal', 'paused', 1, 'one'))
        conn.close()
        self.run.reset_mock()
        self.worker.reply('one', 'p/terminal', 'final answer')
        self.assertEqual(self.run.call_count, 1)
        self.worker.reply('one', 'p/terminal', 'paused')
        self.assertEqual(self.run.call_count, 1)

    def test_proven_envelope_copies_share_one_job(self):
        now = int(time.time() * 1000)
        with sqlite3.connect(str(aw.NETWORK_DB)) as db:
            for mid in ('original', 'local-copy'):
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)',
                           (mid, 'p/terminal', self.worker.address, '[Group room "dev"]\nPR #11', now, None))
        db.close()
        self.worker.ingest()
        self.assertEqual(self.worker.journal.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)
        (self.root / 'relay.json').write_text(json.dumps({'sent': {'original': {
            'core': 'PR #11', 'speaker': 'p/lead', 'room': 'r', 'to': self.worker.address, 'at': now}}}))
        self.worker.ingest()
        self.assertEqual([row[0] for row in self.worker.journal.db.execute('SELECT id FROM jobs')], ['original'])

    def test_missing_room_metadata_expires_without_model_call(self):
        message = json.loads(self.job(body='[Group room "dev"]\nPR #11')['payload'])
        message['sent_at'] -= 31000
        with self.assertRaises(aw.RequestError):
            self.worker.request(message)

    def test_reader_uses_writer_lock_and_only_one_snapshot_per_ingest(self):
        with mock.patch('storage.file_lock') as lock:
            self.worker.relay_records()
        lock.assert_called_once_with(self.root / 'relay.state.lock')
        with sqlite3.connect(str(aw.NETWORK_DB)) as db:
            for mid in ('first', 'second'):
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)',
                           (mid, 'p/terminal', self.worker.address, '[Group room "dev"]\n/status', int(time.time() * 1000), None))
        db.close()
        with mock.patch.object(self.worker, 'relay_records', return_value={}) as read:
            self.worker.ingest()
        read.assert_called_once()

    def test_posting_reuses_marker_and_stops_when_head_changed(self):
        self.worker.github_author = lambda: 'gemini-ehojune[bot]'
        body = '<!-- reason-gemini-review:one -->\nbody'
        existing = {'id': 2, 'commit_id': 'a' * 40, 'body': body, 'user': {'login': 'gemini-ehojune[bot]'}, 'html_url': 'receipt'}
        self.worker.gh_json = mock.Mock(return_value=[[existing]])
        self.assertEqual(self.worker.publish('one', ('p/repo', 1), 'a' * 40, body), 'receipt')
        self.assertEqual(self.worker.gh_json.call_count, 1)
        self.worker.gh_json = mock.Mock(side_effect=[[], {'headRefOid': 'b' * 40}])
        with self.assertRaises(aw.RequestError):
            self.worker.publish('one', ('p/repo', 1), 'a' * 40, 'body')
        self.assertEqual(self.worker.gh_json.call_count, 2)  # no write

    def test_current_response_wins_over_stale_schema_metadata(self):
        head = 'a' * 40
        current = {'head': head, 'summary': 'current', 'findings': []}
        self.assertEqual(aw.review_result(json.dumps(current) + '\n' + json.dumps(current), head), current)
        self.assertEqual(aw.review_result(json.dumps(current) + '\n' + json.dumps({'summary': 'old format', 'findings': []}), head), current)
        with self.assertRaises(aw.WorkerError):
            aw.review_result(json.dumps({**current, 'head': 'old'}), head)
        self.worker.github_author = lambda: 'gemini-ehojune[bot]'
        marker = '<!-- reason-gemini-review:one -->'
        existing = {'id': 2, 'commit_id': head, 'body': marker + '\nstale schema text',
                    'user': {'login': 'gemini-ehojune[bot]'}, 'html_url': 'receipt'}
        corrected = {**existing, 'body': marker + '\ncurrent'}
        self.worker.gh_json = mock.Mock(side_effect=[[[existing]], corrected])
        self.assertEqual(self.worker.publish('one', ('p/repo', 1), head, corrected['body']), 'receipt')
        self.assertIn('PUT', self.worker.gh_json.call_args.args)

    def test_room_conversation_survives_next_message_without_repeating_model(self):
        self.worker.reply = mock.Mock()
        self.worker.model_call = mock.Mock(return_value={'status': 'SUCCESS', 'response': 'remembered', 'conversation_id': 'persisted'})
        self.worker.process(self.job())
        row = self.worker.journal.db.execute('SELECT * FROM jobs WHERE id=?', ('one',)).fetchone()
        self.assertEqual(row['status'], 'done')
        self.assertEqual(self.worker.journal.db.execute('SELECT id FROM conversations').fetchone()[0], 'persisted')
        self.worker.journal.update('one', status='outbox')
        self.worker.process(self.worker.journal.db.execute('SELECT * FROM jobs WHERE id=?', ('one',)).fetchone())
        self.assertEqual(self.worker.model_call.call_count, 1)

    def test_no_github_identity_or_token_helper_means_no_personal_fallback(self):
        with self.assertRaises(aw.WorkerError):
            self.worker.github_author()
        self.worker.gh = 'gh'
        self.worker.github_author = lambda: 'gemini-ehojune[bot]'
        self.run.reset_mock()
        with self.assertRaises(aw.WorkerError):
            self.worker.gh_json('api', 'anything')
        self.run.assert_not_called()

    def test_wrong_token_identity_is_rejected_before_requested_api_call(self):
        self.worker.gh = 'gh'
        self.worker.github_author = lambda: 'gemini-ehojune[bot]'
        helper = self.root / 'bin/gh-agent-token.py'
        helper.parent.mkdir()
        helper.touch()
        self.run.reset_mock()
        self.run.side_effect = ['token', json.dumps({'data': {'viewer': {'login': 'wrong[bot]'}}})]
        with self.assertRaises(aw.WorkerError):
            self.worker.gh_json('api', 'repos/p/r/pulls/1/reviews', '--input', 'body.json')
        self.assertEqual(self.run.call_count, 2)
        self.assertIn('graphql', self.run.call_args.args[0])

    def test_severity_schema_and_model_footer(self):
        good = {'summary': 'result', 'findings': [{'severity': 'P1', 'title': 'Missing cancellation',
                'body': 'Concrete evidence', 'path': 'a.py', 'line': 5}]}
        text = aw.review_text(good, 'p/repo', 1, 'a' * 40, 'marker', 'flash')
        self.assertIn('[P1]', text)
        self.assertIn('Co-Authored-By: Gemini (flash)', text)
        for key, value in (('severity', 'P9'), ('line', 0), ('line', True)):
            bad = {'summary': 'result', 'findings': [{**good['findings'][0], key: value}]}
            with self.assertRaises(aw.WorkerError):
                aw.review_text(bad, 'p/repo', 1, 'a' * 40, 'marker', 'flash')

    def room_job(self, mid, core):
        now = int(time.time() * 1000)
        with sqlite3.connect(str(aw.NETWORK_DB)) as db:
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', (mid, 'p/terminal', self.worker.address, '[Group room "dev"]\n---\n' + core, now, None))
        db.close()
        (self.root / 'relay.json').write_text(json.dumps({'sent': {mid: {
            'core': core, 'speaker': 'p/terminal', 'room': 'r', 'to': self.worker.address, 'at': now}}}))
        self.worker.ingest()
        return self.worker.journal.db.execute('SELECT * FROM jobs WHERE id=?', (mid,)).fetchone()

    def test_notice_with_example_mention_is_not_a_request(self):
        # Shape of 01M61YEHR31QP3VG5QAZZEV08Y: addressed to the lead, names the reviewer only as a usage example.
        core = ('@claude-tech-lead 인계 안내입니다. https://github.com/p/other/pull/54\n'
                '새 리뷰어는 방의 @gemini-reviewer + 전체 PR URL로 호출합니다.')
        job = self.room_job('notice', core)
        self.run.reset_mock()
        with mock.patch.object(self.worker, 'model_call') as model:
            self.worker.process(job)
        model.assert_not_called()
        self.assertEqual(self.run.call_count, 0)  # no reply either
        row = self.worker.journal.db.execute("SELECT status FROM jobs WHERE id='notice'").fetchone()
        self.assertEqual(row[0], 'ignored')
        self.assertIsNone(self.worker.journal.get('paused'))

    def test_addressed_to_reads_only_the_leading_mentions(self):
        self.assertTrue(aw.addressed_to('@gemini-reviewer https://github.com/p/r/pull/1', 'gemini-reviewer'))
        self.assertTrue(aw.addressed_to('  @claude-tech-lead, @gemini-reviewer review', 'gemini-reviewer'))
        self.assertFalse(aw.addressed_to('@claude-tech-lead call @gemini-reviewer', 'gemini-reviewer'))
        self.assertFalse(aw.addressed_to('PR #1 for @gemini-reviewer', 'gemini-reviewer'))
        self.assertFalse(aw.addressed_to('@gemini-reviewer-2 review', 'gemini-reviewer'))
        self.assertTrue(aw.addressed_to('@p/gemini-reviewer review', 'gemini-reviewer', 'p/gemini-reviewer'))
        self.assertFalse(aw.addressed_to('@other/gemini-reviewer review', 'gemini-reviewer', 'p/gemini-reviewer'))
        self.assertTrue(aw.addressed_to('@gemini-reviewer review', 'gemini-reviewer', 'p/gemini-reviewer'))

    def test_prompt_carries_reviewer_rules(self):
        job = self.room_job('ask', '@gemini-reviewer 설명해 주세요')
        good = {'status': 'SUCCESS', 'response': 'ok', 'conversation_id': 'c1'}
        with mock.patch.object(self.worker, 'model_call', return_value=good) as model:
            self.worker.process(job)
        prompt = model.call_args.args[0]
        for part in ('Caller: p/terminal', 'gemini-reviewer', 'Forbidden', 'head SHA', 'P0 critical'):
            self.assertIn(part, prompt)

    def test_timeout_is_configurable_and_grows_with_prompt_to_a_cap(self):
        self.assertEqual(aw.call_timeout('x'), 300)
        self.assertEqual(aw.call_timeout('x' * 100000), 300 + 15 * 10)
        self.assertEqual(aw.call_timeout('x' * 10_000_000), 900)
        self.assertEqual(aw.call_timeout('x', 60, 120), 60)
        slow = aw.Worker('slow-reviewer', self.root, 'agy', 'reason-network', 'm', 'p/repo', 120, 240)
        self.addCleanup(slow.journal.db.close)
        self.run.reset_mock()
        self.run.return_value = json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': 'ok', 'conversation_id': 'c'}})
        slow.model_call('hi', 'k')
        args = self.run.call_args.args[0]
        self.assertEqual(args[args.index('--print-timeout') + 1], '120s')
        self.assertEqual(self.run.call_args.kwargs['timeout'], 150)

    def test_failure_report_names_cause_and_log_and_is_never_a_pass(self):
        logs = self.root / 'agylog'
        logs.mkdir()
        (logs / 'cli-1.log').write_text('W1027 poll.go:188] Print mode: print timeout after 5m0s with turn in progress', encoding='utf-8')
        text = aw.diagnose(aw.WorkerError('No successful, nonempty model result.'), logs)
        self.assertIn('cause=timeout', text)
        self.assertIn('cli-1.log', text)
        # A stale timeout line in the shared log must not override the current, different error.
        self.assertIn('cause=auth', aw.diagnose(aw.WorkerError('HTTP 401 unauthenticated'), logs))
        (logs / 'cli-2.log').write_text('rpc error: code = 429 RESOURCE_EXHAUSTED quota', encoding='utf-8')
        import os
        os.utime(logs / 'cli-2.log', (time.time() + 5, time.time() + 5))
        self.assertIn('cause=quota', aw.diagnose(aw.WorkerError('x'), logs))
        self.assertIn('cause=auth', aw.diagnose(aw.WorkerError('401 unauthenticated'), self.root / 'none'))
        for code, cause in (('HTTP 403', 'auth'), ('HTTP 401', 'auth'), ('status 429', 'quota')):
            self.assertIn('cause=' + cause, aw.diagnose(aw.WorkerError(code), self.root / 'none'))
        self.assertIn('cause=unknown', aw.diagnose(aw.WorkerError('port 14290 closed'), self.root / 'none'))
        self.assertIn('cause=abnormal exit', aw.diagnose(aw.WorkerError('Command failed'), self.root / 'none'))
        with mock.patch.object(aw.subprocess, 'run', side_effect=aw.subprocess.TimeoutExpired('agy', 330)):
            self.command.stop()
            try:
                with self.assertRaisesRegex(aw.WorkerError, 'timed out after 330'):
                    aw.checked_run(['agy'], timeout=330)
            finally:
                self.command.start()


class LauncherReceiverTests(unittest.TestCase):
    def test_parser_discovers_wmi_python_receiver(self):
        args = ['python.exe', 'C:\\repo\\antigravity_worker.py', '--name', 'gemini-reviewer', '--cwd', 'C:\\work', '--model', 'gemini-3.8-flash-high']
        self.assertEqual(launcher.parse_serve(args)['family'], 'antigravity')
        with mock.patch.object(launcher, 'model_from_args', return_value=(None, None)):
            self.assertEqual(launcher.found_workers([(10, 1, 'python.exe', args)])[0]['name'], 'gemini-reviewer')

    def test_start_uses_wmi_and_gemini_identity_without_inherited_tokens(self):
        instance = launcher.Launcher('reason', None)
        with mock.patch.object(launcher, 'STATE', Path(tempfile.mkdtemp())), \
                mock.patch.object(launcher, 'base_env', return_value={'GH_TOKEN': 'codex-token', 'GITHUB_TOKEN': 'other-token'}), \
                mock.patch.object(launcher, 'find_agy', return_value='agy.exe'), \
                mock.patch.object(launcher, 'find_reason_network', return_value='reason-network.exe'), \
                mock.patch.object(launcher, 'spawn_receiver', return_value=123) as spawn, \
                mock.patch.object(launcher, 'started_at', return_value='born'), mock.patch.object(launcher, 'record_spawn'):
            result = instance.start_worker({'id': 'antigravity'}, 'C:/work', 'gemini-3.8-flash', 'high', 'reviewer')
            self.assertEqual(result['family'], 'antigravity')
            env = spawn.call_args.args[2]
            self.assertEqual(env['LABHQ_COMMIT_AGENT'], 'gemini')
            self.assertNotIn('GH_TOKEN', env)
            self.assertNotIn('GITHUB_TOKEN', env)
            with self.assertRaises(launcher.LaunchError):
                instance.start_worker({'id': 'antigravity'}, 'C:/work', '', '', 'reviewer')
            with self.assertRaises(launcher.LaunchError):
                instance.start_worker({'id': 'antigravity'}, 'C:/work', 'gemini-3.8-flash', 'high', 'reviewer', True)
            with mock.patch.object(launcher, 'find_agy', return_value=None):
                with self.assertRaises(launcher.LaunchError):
                    instance.start_worker({'id': 'antigravity'}, 'C:/work', 'gemini-3.8-flash', 'low', 'reviewer')


if __name__ == '__main__':
    unittest.main()
