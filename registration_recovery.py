"""Bounded local recovery for proven idle, owned native receivers. No model calls."""
import json
import re
from pathlib import Path
import time

from storage import atomic_json

ERROR = "network: this session isn't registered with Reason Network; restart the agent session, or use the reason-network tools; reconnecting"


def registration_error(log):
    try:
        with Path(log).open('rb') as f:
            f.seek(max(0, f.seek(0, 2) - 262144))
            lines = f.read().decode('utf-8', 'replace').splitlines()
    except OSError:
        return False
    # A new receiver or successful reply supersedes old failures.
    count = 0
    for line in lines:
        line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        if ' takes work on Reason Network ' in line or line.startswith('→ '):
            count = 0
        if line.strip() == ERROR:
            count += 1
    return count >= 2


def repair(launcher, worker, observe):
    from claude_context import paused_ingress
    from launcher import kill_tree, HOME
    name = worker['name']
    # The normal operation context locks across processes and reloads shared records.
    # Do not hold self.lock during settle().
    with launcher.operation():
        with launcher.lock:
            if launcher.workers.get(name) != worker or name in launcher.restarting or not launcher.alive(worker):
                raise ValueError('Worker identity changed')
            recorded = dict(launcher.records.get(name) or worker)
        if worker['family'] == 'claude' and not worker.get('claudeContext'):
            raise ValueError('Legacy Claude needs explicit context migration')
        def idle():
            state = observe(name)
            if state['status'] != 'idle' or state['pending']:
                raise ValueError('Worker busy or pending; retained')
            path = HOME / '.reason' / 'ask-workers' / (name + '.json')
            # Also protect answered-but-unpublished requests, not only unfinished model calls.
            if path.exists() and json.loads(path.read_text(encoding='utf-8')):
                raise ValueError('Native outbox is not empty; retained')
        idle()
        with paused_ingress(worker['pid']):
            idle()  # requests accepted before suspension must have reached the durable native queue
            kill_tree(worker['pid'])
            if not launcher.wait_context_exit(worker):
                raise ValueError('Receiver termination uncertain; no second receiver started')
        with launcher.lock:
            launcher.restarting.add(name)
        try:
            family = launcher.catalog.family(recorded.get('family') or worker['family'])
            replacement = launcher.start_worker(family, recorded.get('cwd') or worker['cwd'], recorded.get('model') or '',
                recorded.get('effort') or '', name, bool(recorded.get('fullAccess', worker.get('fullAccess'))),
                recorded.get('fast', worker.get('fast')))
            with launcher.lock:
                launcher.workers[name] = replacement
                launcher.save()
                launcher.remember(replacement)
            launcher.settle(replacement)
        finally:
            with launcher.lock:
                launcher.restarting.discard(name)


def tick(launcher):
    from assignments import live_observer
    from launcher import HOME, STATE
    path = STATE / 'registration-recovery.json'
    records = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    with launcher.lock:
        workers = [dict(w) for w in launcher.workers.values()]
    for worker in workers:
        if worker['family'] not in ('claude', 'codex') or not registration_error(worker.get('log', '')):
            continue
        name = worker['name']
        previous = records.get(name, {})
        now = time.time()
        if previous.get('attempts', 0) >= 3 or now - previous.get('at', 0) < 300:
            continue
        observe = live_observer(HOME / '.reason', STATE)
        try:
            state = observe(name)
            if state['status'] != 'idle' or state['pending']:
                continue
        except Exception:
            continue
        records[name] = {'at': now, 'pid': worker['pid'], 'attempts': previous.get('attempts', 0)+1,
                         'status': 'attempting'}
        atomic_json(path, records, durable=True)  # crash cannot silently reset the attempt budget
        try:
            repair(launcher, worker, observe)
            records[name]['status'] = 'restarted-awaiting-response'
        except Exception as exc:
            records[name].update(status='held', error=str(exc))
        atomic_json(path, records, durable=True)
