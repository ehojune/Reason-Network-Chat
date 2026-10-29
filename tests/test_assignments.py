import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import assignments
from assignments import Registry, Conflict, paths


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.state={'status':'idle','live':True,'pending':[]}
        self.registry=Registry(Path(self.tmp.name)/'assignments.json',lambda _:self.state)
        self.task='https://github.com/team/repo/issues/1'

    def apply(self,action,owner='w1',revision=1,**kwargs):
        return self.registry.apply(action,self.task,owner,revision,**kwargs)

    def test_active_handoff_and_old_revision_cannot_run(self):
        self.apply('claim',revision=0)
        self.apply('begin')
        with self.assertRaises(Conflict):self.apply('claim','w2',note='transfer')
        self.apply('finish',note='PR #2; working tree preserved')
        self.apply('claim','w2',note='PR #2 handoff')
        with self.assertRaises(Conflict):self.apply('begin')
        self.apply('begin','w2',2)
        with self.assertRaises(Conflict):self.apply('begin','w2',2)

    def test_pending_cancel_or_busy_worker_blocks_handoff_without_changes(self):
        self.apply('claim',revision=0)
        before=self.registry.path.read_bytes()
        for state in ({'status':'busy','live':True,'pending':[]},
                      {'status':'idle','live':True,'pending':['old','cancel']},
                      {'status':'unknown','live':False,'pending':[]}):
            self.state=state
            with self.assertRaises(Conflict):self.apply('claim','w2',note='handoff')
            self.assertEqual(self.registry.path.read_bytes(),before)

    def test_scope_overlap_across_worktrees_and_parallel_claims(self):
        self.apply('claim',revision=0,scope=['src/'])
        with self.assertRaises(Conflict):
            self.registry.apply('claim','https://github.com/TEAM/REPO/issues/2','w2',0,['src/main.py'])
        self.registry.apply('claim','https://github.com/team/repo/issues/3','w3',0,['tests'])
        self.apply('begin',scope=['src/main.py'])
        with self.assertRaises(Conflict):self.apply('check',scope=['README.md'])

    def test_only_one_concurrent_writer_claims_repository(self):
        def claim(n):
            try:self.registry.apply('claim',f'https://github.com/team/repo/issues/{n}','w'+str(n),0);return True
            except Conflict:return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(claim,[1,2])),1)

    def test_finished_assignment_is_not_replayed_and_history_is_preserved(self):
        self.apply('claim',revision=0);self.apply('begin');self.apply('finish',note='done')
        with self.assertRaises(Conflict):self.apply('begin')
        self.assertEqual(len(self.registry.read()['history']),3)

    def test_invalid_scope_and_corrupt_registry_fail_closed(self):
        for path in ('../a','/tmp/a','C:/a','src//a','src/./a','src/*','src.','src /file.py','src/file.py.'):
            with self.assertRaises(Conflict):paths([path])
        self.registry.path.write_text('{broken')
        with self.assertRaises(ValueError):self.apply('claim',revision=0)

    def test_unavailable_observation_does_not_claim(self):
        def unavailable(_):raise OSError('offline')
        self.registry.observe=unavailable
        with self.assertRaises(OSError):self.apply('claim',revision=0)
        self.assertFalse(self.registry.path.exists())

    def test_observer_refreshes_native_status_and_refuses_remote_identity(self):
        root=Path(self.tmp.name);(root/'ask-workers').mkdir()
        (root/'ask-workers/w1.json').write_text('[]')
        idle={'person':'me','machine':'local','sessions':[{'name':'w1','worker':True,'person':'me','machine':'local','status':'idle'}]}
        busy=json.loads(json.dumps(idle));busy['sessions'][0]['status']='busy'
        remote=json.loads(json.dumps(idle));remote['sessions'][0]['machine']='remote'
        observer=assignments.live_observer(root)
        with patch.object(assignments,'fresh_sessions',side_effect=[idle,idle,busy,busy,remote]) as fresh:
            self.assertEqual(observer('w1')['status'],'idle')
            self.assertEqual(observer('w1')['status'],'busy')
            with self.assertRaises(Conflict):observer('w1')
            self.assertEqual(fresh.call_count,5)

        with patch.object(assignments,'fresh_sessions',side_effect=[idle,busy]):
            with self.assertRaises(Conflict):observer('w1')

    def test_new_listener_requires_live_launcher_proof(self):
        root=Path(self.tmp.name);(root/'ask-workers').mkdir()
        (root/'ask-workers/w1.json').write_text('[]')
        observer=assignments.live_observer(root,root)
        with patch.object(assignments,'fresh_sessions',return_value={'person':'me','machine':'local','sessions':[]}), \
             patch.object(assignments,'managed_idle',return_value=True) as proof:
            self.assertEqual(observer('w1')['status'],'idle')
            self.assertEqual(proof.call_count,2)
            proof.return_value=False
            with self.assertRaises(Conflict):observer('w1')

    def test_case_sensitive_scope_cannot_authorize_distinct_file(self):
        with patch.object(assignments.sys,'platform','linux'):
            self.apply('claim',revision=0,scope=['src/Foo.py']);self.apply('begin')
            with self.assertRaises(Conflict):self.apply('check',scope=['src/foo.py'])

    def test_launcher_proof_rejects_reused_pid_and_running_child(self):
        root=Path(self.tmp.name)
        (root/'workers.json').write_text(json.dumps([{'name':'w1','pid':123,'started':'birth'}]))
        procs=[(123,1,'reason',['reason','network','serve','codex','--name','w1'])]
        with patch('launcher.started_at',return_value='birth') as born, \
             patch('launcher.list_processes',return_value=procs) as processes:
            self.assertTrue(assignments.managed_idle('w1',root))
            processes.return_value=procs+[(124,123,'codex',['codex','exec'])]
            self.assertFalse(assignments.managed_idle('w1',root))
            processes.return_value=procs;born.return_value='reused'
            self.assertFalse(assignments.managed_idle('w1',root))
