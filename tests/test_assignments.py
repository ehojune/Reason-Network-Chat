import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
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
            self.registry.apply('claim','https://github.com/TEAM/REPO/issues/2','w2',0,['SRC/main.py'])
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
        for path in ('../a','/tmp/a','C:/a','src//a','src/./a','src/*'):
            with self.assertRaises(Conflict):paths([path])
        self.registry.path.write_text('{broken')
        with self.assertRaises(ValueError):self.apply('claim',revision=0)

    def test_unavailable_observation_does_not_claim(self):
        def unavailable(_):raise OSError('offline')
        self.registry.observe=unavailable
        with self.assertRaises(OSError):self.apply('claim',revision=0)
        self.assertFalse(self.registry.path.exists())
