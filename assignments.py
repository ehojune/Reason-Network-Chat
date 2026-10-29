"""Cooperative task ownership with revision checks; never writes Reason queues.

Leads claim before dispatch. Workers begin before edits and finish before handoff.
This is a coordination gate for cooperating agents, not an OS access control.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from storage import atomic_json, file_lock


class Conflict(ValueError):
    pass


def task_key(value):
    m = re.fullmatch(r'https://github\.com/([^/\s]+)/([^/\s]+)/(issues|pull)/(\d+)/?', value)
    if not m:
        raise Conflict('task must be a GitHub issue or pull-request URL')
    repo = (m[1]+'/'+m[2]).casefold()
    return repo+'#'+m[4], repo


def paths(values):
    out=[]
    for value in values or ['.']:
        value=value.replace('\\','/').rstrip('/')
        parts=value.split('/')
        if value!='.' and (not value or value.startswith('/') or any(p in ('','..','.') or p.endswith((' ','.')) for p in parts)
                           or re.search(r'[:*?\[\]\x00-\x1f]',value)):
            raise Conflict('scope must be a literal repository-relative path or .')
        out.append(value.casefold() if sys.platform=='win32' else value)
    return sorted(set(out))


def covers(parent, child):
    return parent=='.' or parent==child or child.startswith(parent+'/')


def checkout_paths(values, root):
    chosen=paths(values)
    if not root:return chosen
    base=Path(root)
    # Path.resolve expands Win32 8.3 aliases, including an existing parent of
    # a file that has not been created yet. Link rejection happens first.
    return paths([(base/value).resolve().relative_to(base).as_posix() for value in chosen])


def overlap(a,b):
    # Conservative across Windows/default macOS and case-sensitive volumes.
    # Containment checks retain exact case off Windows; overlap may refuse a
    # harmless case-only parallel assignment, never grant an aliased writer.
    canonical=lambda p:unicodedata.normalize('NFC',p.casefold())
    return any(covers(canonical(x),canonical(y)) or covers(canonical(y),canonical(x)) for x in a for y in b)


def verify_tree(root, repo, scopes):
    """Scoped parallel writes need a real checkout, not an unverifiable path label."""
    if not root:
        if scopes==['.']:return None
        raise Conflict('scoped claims require --repo-root pointing to the worker checkout')
    root=Path(root).resolve(strict=True)
    def git(*args):
        p=subprocess.run(['git','-C',str(root),*args],capture_output=True,timeout=10)
        if p.returncode:raise Conflict('cannot verify assignment checkout')
        return p.stdout.decode('utf-8').strip()
    if Path(git('rev-parse','--show-toplevel')).resolve()!=root:
        raise Conflict('--repo-root must be the checkout root')
    remote=git('config','--get','remote.origin.url')
    match=re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+/[^/\s]+?)(?:\.git)?/?',remote)
    if not match or match[1].casefold()!=repo:
        raise Conflict('checkout origin does not match the task repository')
    def plain(path):
        try:info=path.lstat()
        except FileNotFoundError:return
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400 or (stat.S_ISREG(info.st_mode) and info.st_nlink>1):
            raise Conflict('linked/reparse/hard-linked scope refused: '+str(path.relative_to(root)))
    for scope in scopes:
        current=root
        for part in ([] if scope=='.' else scope.split('/')):
            current=current/part;plain(current)
        # Whole-repository reservation cannot overlap another task in this repo.
        if scope=='.':continue
        if not current.is_dir():continue  # a literal file or a not-yet-created path
        def fail(exc):raise exc
        for folder,dirs,files in os.walk(current,followlinks=False,onerror=fail):
            for name in dirs+files:plain(Path(folder)/name)
    return str(root)


def fresh_sessions():
    from launcher import base_env
    exe=os.environ.get('REASON_BIN')
    if not exe and sys.platform=='win32':
        candidate=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'Reason/bin/reason.exe'
        if candidate.is_file():exe=str(candidate)
    exe=exe or shutil.which('reason')
    if not exe or (sys.platform=='win32' and not exe.lower().endswith('.exe')):
        raise Conflict('native Reason executable unavailable')
    result=subprocess.run([exe,'network','who','--all','--json'],stdin=subprocess.DEVNULL,
        capture_output=True,timeout=20,env=base_env(),creationflags=0x08000000 if sys.platform=='win32' else 0)
    if result.returncode:raise Conflict('fresh Reason worker status unavailable')
    return json.loads(result.stdout.decode('utf-8'))


def managed_proof(owner, chat_home):
    """Read launcher PID/birth proof without constructing a mutating Launcher."""
    from launcher import started_at, list_processes, descendants, parse_serve
    rows=json.loads((Path(chat_home)/'workers.json').read_text(encoding='utf-8'))
    found=[w for w in rows if w.get('name')==owner]
    if len(found)!=1:return False
    w=found[0]
    if not w.get('started') or started_at(w['pid'])!=w['started']:return False
    procs=list_processes()
    if procs is None:return False
    roots=[p for p in procs if p[0]==w['pid']]
    if len(roots)!=1 or (parse_serve(roots[0][3]) or {}).get('name')!=owner:return False
    if started_at(w['pid'])!=w['started']:return False
    # conhost belongs to an idle Windows listener too. Claude can keep its
    # stream-json agent alive across turns; native status determines its busy state.
    children=[p for p in descendants(procs,w['pid']) if p[2].lower()!='conhost.exe']
    return {'pid':w['pid'],'started':w['started'],'agentChildren':bool(children)}


def live_observer(reason_home, chat_home=None):
    """Read evidence fresh under the assignment lock; unavailable is not idle."""
    def observe(owner):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',owner):
            raise Conflict('invalid worker name')
        def status():
            state=fresh_sessions()
            if not state.get('person') or not state.get('machine'):
                raise Conflict('worker state unavailable')
            # Native sessions can outlive an uncleanly terminated serve process.
            proof=managed_proof(owner,chat_home) if chat_home else None
            if not proof:
                raise Conflict('live launcher/process proof unavailable: '+owner)
            named=[s for s in state.get('sessions',[]) if s.get('name')==owner]
            matches=[s for s in named if s.get('person')==state['person']
                     and s.get('machine') in (None,state['machine'])]
            identity=(proof['pid'],proof['started'])
            if len(matches)==1:return (state['person'],state['machine'],matches[0].get('status'))+identity
            # A newly launched listener has no native session until its first request.
            if not named and not proof['agentChildren']:
                return (state['person'],state['machine'],'idle')+identity
            raise Conflict('worker identity missing or ambiguous: '+owner)
        def queue():
            queue_name=re.sub(r'[^a-zA-Z0-9-]','-',owner)
            try:raw=(Path(reason_home)/'ask-workers'/(queue_name+'.json')).read_text(encoding='utf-8')
            except FileNotFoundError:return []  # a verified new listener has no queue yet
            rows=json.loads(raw)
            if not isinstance(rows,list) or any(not isinstance(x,dict) or not isinstance(x.get('request'),dict) for x in rows):
                raise Conflict('worker queue unavailable: '+owner)
            return [x for x in rows if 'reply' not in x]
        before=status();first=queue();after=status();second=queue()
        if before!=after or first!=second:
            raise Conflict('worker status/queue changed during observation: '+owner)
        return {'status':after[2], 'live':True, 'pending':[x['request'].get('id') for x in second]}
    return observe


class Registry:
    def __init__(self,path,observe,repo_root=None):
        self.path=Path(path)
        self.observe=observe
        self.repo_root=repo_root

    def read(self):
        if not self.path.exists():return {'version':1,'tasks':{}}
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('version')!=1 or not isinstance(data.get('tasks'),dict):
            raise Conflict('assignment registry unavailable')
        return data

    def idle(self,owner):
        obs=self.observe(owner)
        if obs.get('status')!='idle' or obs.get('live') is not True or obs.get('pending') != []:
            raise Conflict('handoff/claim blocked: '+owner+' must be live idle with an empty queue; '+json.dumps(obs))
        return obs

    def apply(self,action,task,owner,revision,scope=None,note=''):
        key,repo=task_key(task)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',owner):raise Conflict('invalid worker name')
        if revision<0:raise Conflict('revision must be nonnegative')
        with file_lock(self.path.with_suffix('.lock')):
            data=self.read();old=data['tasks'].get(key)
            if (old or {}).get('revision',0)!=revision:
                raise Conflict('stale assignment revision; read assignment list before retrying')
            if action=='claim':
                chosen=paths(scope)
                checkout=verify_tree(self.repo_root,repo,chosen)
                chosen=checkout_paths(chosen,checkout)
                if old:
                    if old['state']=='working':raise Conflict('active worker must finish before handoff')
                    if not note.strip():raise Conflict('handoff needs a result/preserved-work reference')
                    if old['state']!='done':self.idle(old['owner'])
                self.idle(owner)
                for other_key,other in data['tasks'].items():
                    if other_key!=key and other['repo']==repo and other['state']!='done' and overlap(chosen,other['paths']):
                        raise Conflict('scope overlaps '+other['task']+' owned by '+other['owner'])
                row={'task':task,'repo':repo,'owner':owner,'revision':revision+1,
                     'paths':chosen,'repoRoot':checkout,'state':'assigned','note':note,'updatedAt':int(time.time()*1000)}
            else:
                if not old or old['owner']!=owner:raise Conflict('not the current task owner')
                row=dict(old)
                if action in ('begin','check') and old.get('repoRoot'):
                    if self.repo_root and str(Path(self.repo_root).resolve())!=old['repoRoot']:
                        raise Conflict('use the checkout registered with this assignment')
                    verify_tree(old['repoRoot'],repo,old['paths']+(paths(scope) if scope else []))
                if action=='begin':
                    if old['state']!='assigned':raise Conflict('assignment already started or finished; do not replay it')
                    if scope and any(not any(covers(p,x) for p in old['paths']) for x in checkout_paths(scope,old.get('repoRoot'))):
                        raise Conflict('requested files are outside assigned scope')
                    row['state']='working'
                elif action=='finish':
                    if old['state']!='working':raise Conflict('only a working assignment can finish')
                    if not note.strip():raise Conflict('finish needs a result/preserved-work reference')
                    row.update(state='done',note=note)
                elif action=='check':
                    if old['state']!='working':raise Conflict('task is not working; begin first')
                    if scope and any(not any(covers(p,x) for p in old['paths']) for x in checkout_paths(scope,old.get('repoRoot'))):
                        raise Conflict('requested files are outside assigned scope')
                    return row
                else:raise Conflict('unknown action')
                row['updatedAt']=int(time.time()*1000)
            # Keep prior transitions as evidence, never delete tasks to reset revisions.
            data.setdefault('history',[]).append({'action':action,'before':old,'after':row})
            data['tasks'][key]=row
            atomic_json(self.path,data,durable=True)
            return row


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['list','claim','begin','check','finish'])
    p.add_argument('task',nargs='?')
    p.add_argument('--owner')
    p.add_argument('--revision',type=int)
    p.add_argument('--path',action='append',dest='paths')
    p.add_argument('--note',default='')
    p.add_argument('--repo-root',type=Path,help='worker checkout root; required for scoped parallel claims')
    p.add_argument('--chat-home',type=Path,default=Path(os.environ.get('REASON_CHAT_HOME',Path.home()/'.reason-network-chat')))
    p.add_argument('--reason-home',type=Path,default=Path.home()/'.reason')
    a=p.parse_args(argv)
    if a.action!='list' and (not a.task or not a.owner or a.revision is None):
        p.error('task URL, --owner and --revision are required')
    try:
        registry=Registry(a.chat_home/'assignments.json',live_observer(a.reason_home,a.chat_home),a.repo_root)
        out=registry.read() if a.action=='list' else registry.apply(a.action,a.task,a.owner,a.revision,a.paths,a.note)
        print(json.dumps(out,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError,TimeoutError,subprocess.TimeoutExpired) as exc:
        print('Assignment refused: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
