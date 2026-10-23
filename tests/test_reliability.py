import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault('REASON_CHAT_HOME', tempfile.mkdtemp())
os.environ.setdefault('REASON_BIN', sys.executable)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
import server


class EndpointTest(unittest.TestCase):
    def handler(self, path, headers=None):
        h = server.Handler.__new__(server.Handler)
        h.path, h.headers = path, headers or {}
        h.host_ok = lambda: True
        h.send_json = mock.Mock()
        return h

    def test_refresh_requires_a_token_but_cached_get_does_not(self):
        for token, expected in ((None, 403), ('wrong', 403), (server.TOKEN, 200)):
            h = self.handler('/api/catalog?refresh=1', {'X-Reason-Chat-Token': token} if token else {})
            with mock.patch.object(server.CATALOG, 'get', return_value=[]) as get, mock.patch.object(server, 'folders', return_value=[]):
                h.do_GET()
            self.assertEqual(h.send_json.call_args.args[1] if len(h.send_json.call_args.args) > 1 else 200, expected)
            self.assertEqual(get.call_count, int(expected == 200))
        h = self.handler('/api/catalog')
        with mock.patch.object(server.CATALOG, 'get', return_value=[]) as get, mock.patch.object(server, 'folders', return_value=[]):
            h.do_GET()
        get.assert_called_once_with(False)

    def test_room_save_waits_for_identity(self):
        h = self.handler('/api/rooms/save')
        h.read_json = lambda: {'name':'room','members':['p/terminal']}
        with mock.patch.object(server, 'me_and_known', return_value=(None, {'p/terminal'})), mock.patch.object(server.ROOMS, 'upsert') as save:
            h.do_POST()
        self.assertEqual(h.send_json.call_args.args[1], 503)
        save.assert_not_called()


class RegistryTest(unittest.TestCase):
    def test_two_relay_processes_preserve_queue_claims(self):
        with tempfile.TemporaryDirectory() as home:
            code = '''import json,sys,time
from pathlib import Path
from relay import Relay
r=Relay(sys.argv[1],None,lambda *a: [],lambda *a: (0,'',''))
Path(sys.argv[1],sys.argv[2]+'.ready').touch()
while not Path(sys.argv[1],'go').exists(): time.sleep(.01)
won=r.claim('same','resent')
for i in range(10):
 with r.transaction():
  with r.lock:
   r.queue.setdefault('room',[]).append({'reply':sys.argv[2]+str(i),'to':'p/a','sender':'p/b','body':'message','hop':1,'flight':{'body':sys.argv[2]+str(i),'me':'p/terminal','newest':0}})
   r.save(strict=True)
Path(sys.argv[1],sys.argv[2]+'.result').write_text(json.dumps(won))
'''
            children=[subprocess.Popen([sys.executable,'-c',code,home,name],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for name in ('one','two')]
            try:
                import time
                deadline=time.monotonic()+10
                while not all(Path(home,n+'.ready').exists() for n in ('one','two')):
                    if time.monotonic()>deadline: self.fail('relay writers did not start')
                    time.sleep(.02)
                Path(home,'go').touch()
                for p in children:
                    out,err=p.communicate(timeout=20)
                    self.assertEqual(p.returncode,0,err.decode())
                data=json.loads(Path(home,'relay.json').read_text())
                self.assertEqual(len(data['queue']['room']),20)
                self.assertEqual(len({x['flight']['body'] for x in data['queue']['room']}),20)
                self.assertEqual(sum(json.loads(Path(home,n+'.result').read_text()) for n in ('one','two')),1)
                self.assertEqual(list(Path(home).glob('*.tmp')),[])
            finally:
                for p in children:
                    if p.poll() is None: p.kill(); p.communicate()

    def test_two_processes_keep_both_workers_and_records(self):
        with tempfile.TemporaryDirectory() as home:
            code = '''import json, sys, time
from pathlib import Path
import launcher
launcher.STATE=Path(sys.argv[1])
launcher.started_at=lambda pid: 'test'
launcher.Launcher.alive=staticmethod(lambda w: True)
l=launcher.Launcher('reason', None)
Path(sys.argv[1],sys.argv[2]+'.ready').touch()
while not Path(sys.argv[1],'go').exists(): time.sleep(.01)
for i in range(20):
 with l.lock:
  l.workers[sys.argv[2]]={'name':sys.argv[2],'pid':int(sys.argv[3]),'started':'test','family':'codex'}
  l.save()
  l.records[sys.argv[2]]={'name':sys.argv[2],'family':'codex','started':i}
  l.save_records()
'''
            children = [subprocess.Popen([sys.executable, '-c', code, home, name, pid], cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name,pid in [('one','11'),('two','22')]]
            try:
                import time
                deadline=time.monotonic()+10
                while not all(Path(home,n+'.ready').exists() for n in ('one','two')):
                    if time.monotonic() > deadline: self.fail('registry writers did not start')
                    time.sleep(.02)
                Path(home,'go').touch()
                for p in children:
                    out,err=p.communicate(timeout=20)
                    self.assertEqual(p.returncode,0,err.decode())
                workers=json.loads(Path(home,'workers.json').read_text())
                self.assertEqual({w['name'] for w in workers},{'one','two'})
                self.assertEqual(set(json.loads(Path(home,'worker-records.json').read_text())),{'one','two'})
                self.assertEqual(list(Path(home).glob('*.tmp')),[])
            finally:
                for p in children:
                    if p.poll() is None: p.kill(); p.communicate()

    def test_model_detection_ignores_tool_descendants(self):
        procs=[(1,0,'reason',['reason','network','serve','claude','--name','lead']),
               (2,1,'claude',['claude','-p','--model','opus']),
               (3,2,'python',['python','tool.py','--model','fake','--effort','max'])]
        worker=launcher.found_workers(procs)[0]
        self.assertEqual((worker['model'],worker['effort']),('opus',None))

    def test_external_stop_cleans_only_verified_descendant_pids(self):
        l=launcher.Launcher.__new__(launcher.Launcher)
        l.alive=lambda w: False
        procs=[(1,0,'reason',[]),(2,1,'agent',[]),(3,2,'tool',[]),(99,0,'shell',[])]
        with mock.patch.object(launcher,'WIN',False), mock.patch.object(launcher,'list_processes',return_value=procs), mock.patch.object(launcher,'started_at',side_effect=lambda p: str(p)), mock.patch.object(launcher.os,'kill') as kill, mock.patch.object(launcher,'kill_pid') as kill_pid:
            l.halt_external({'pid':1})
        self.assertEqual([x.args[0] for x in kill_pid.call_args_list],[3,2])
        self.assertEqual([x.args[0] for x in kill.call_args_list],[1])
