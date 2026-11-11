"""Durable, sender-isolated Claude stream sessions. Never replay an uncertain turn."""
import hashlib
import contextlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import signal
import time
import uuid

from storage import atomic_json, file_lock


@contextlib.contextmanager
def paused_ingress(pid):
    """Freeze only the verified native listener while inspecting its durable queue.

    Model children keep running. If a turn was accepted before the freeze, its
    durable queue entry makes migration refuse; no busy child is interrupted.
    """
    if os.name != 'nt':
        with paused_posix(pid):
            yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    native = ctypes.WinDLL('ntdll')
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    native.NtSuspendProcess.argtypes = [wintypes.HANDLE]
    native.NtResumeProcess.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x0800, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    suspended = False
    try:
        if native.NtSuspendProcess(handle) != 0:
            raise OSError('Could not pause native listener; no changes applied')
        suspended = True
        yield
    finally:
        if suspended:
            native.NtResumeProcess(handle)  # harmless if this verified idle listener was replaced
        kernel.CloseHandle(handle)


@contextlib.contextmanager
def paused_posix(pid):
    """Stop only the ingress process; confirm it stopped before inspecting its queue."""
    os.kill(pid, signal.SIGSTOP)
    try:
        deadline = time.monotonic() + 3
        while True:
            status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                                    capture_output=True, timeout=2, check=True).stdout.strip()
            if status.startswith(b'T'):
                break
            if time.monotonic() >= deadline:
                raise OSError('Could not confirm stopped listener')
            time.sleep(.02)
        yield
    finally:
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass  # verified idle listener was replaced


def root(settings):
    return Path(settings).parent.parent / 'claude-context' / Path(settings).stem


def identity(message):
    text = message.get('message', {}).get('content')
    if message.get('type') != 'user' or not isinstance(text, str):
        raise ValueError('Expected a native Reason user envelope')
    match = re.match(r"A teammate's agent sent you this message over Reason Network\.\n[^\n]+\n\n"
                     r'<reason-message from="([^"]+)"(?: agent="[^"]*")? id="([^"]+)">\n', text)
    if not match:
        raise ValueError('Missing trusted outer Reason envelope')
    sender, mid = map(html.unescape, match.groups())
    # Reason pools ephemeral ask senders into one conversation.
    peer = re.sub(r'/ask-[0-9a-f]{6}$', '/ask', sender)
    return peer, mid, hashlib.sha256(text.encode()).hexdigest()


def peer_path(settings, peer):
    return root(settings) / (hashlib.sha256(peer.encode()).hexdigest() + '.json')


def read_state(path, peer, cwd):
    if not path.exists():
        return {'version': 1, 'peer': peer, 'cwd': cwd, 'session': str(uuid.uuid4()),
                'started': False, 'pending': None, 'receipts': {}}
    state = json.loads(path.read_text(encoding='utf-8'))
    if (state.get('version') != 1 or state.get('peer') != peer or state.get('cwd') != cwd
            or not isinstance(state.get('receipts'), dict)):
        raise ValueError('Claude conversation identity mismatch')
    uuid.UUID(state['session'])
    return state


def turn(settings, real, args, message, emit, execute=None):
    peer, mid, digest = identity(message)
    path = peer_path(settings, peer)
    with file_lock(path.with_suffix('.lock'), timeout=2):
        state = read_state(path, peer, os.path.normcase(os.path.abspath(os.getcwd())))
        receipt = state['receipts'].get(mid)
        if receipt:
            if receipt['digest'] != digest:
                raise ValueError('Previously answered ID has different contents')
            emit(receipt['result'])
            return
        if state['pending']:
            raise ValueError('Uncertain prior Claude turn held; inspect its transcript before any retry')
        config = json.loads(Path(settings).read_text(encoding='utf-8'))
        extra = config.get('args')
        if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
            raise ValueError('Invalid model settings')
        if any(x in args + extra for x in ('--resume', '-r', '--continue', '-c', '--session-id', '--fork-session')):
            raise ValueError('Caller cannot override the preserved conversation')
        command = [real] + extra + args + [
            '--resume' if state['started'] else '--session-id', state['session']]
        state['pending'] = {'id': mid, 'digest': digest}
        atomic_json(path, state, durable=True)  # before any possible model/tool side effect
        result = None
        def consume(event):
            nonlocal result
            sid = event.get('session_id')
            if sid and sid != state['session']:
                raise ValueError('Claude resumed a different conversation; request held')
            if event.get('type') == 'result':
                if result is not None:
                    raise ValueError('Multiple Claude terminal results')
                result = event
            else:
                emit(event)
        code = (execute or run_child)(command, message, consume)
        if code != 0 or result is None or result.get('is_error') or result.get('session_id') != state['session']:
            raise ValueError('Claude did not complete successfully; request held without replay')
        state.update(started=True, pending=None, model=extra)
        state['receipts'][mid] = {'digest': digest, 'result': result}
        atomic_json(path, state, durable=True)  # persist answer before Reason can acknowledge it
        emit(result)


def run_child(command, message, emit):
    # This child lasts one turn, not a detached service. EOF ends the stream after this input.
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=None, encoding='utf-8', errors='strict', bufsize=1)
    try:
        child.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        child.stdin.close()
        for line in child.stdout:
            event = json.loads(line)
            emit(event)
        return child.wait()
    except BaseException:
        child.terminate()
        child.wait()
        raise
    finally:
        child.stdout.close()


def run(settings, real, args):
    def emit(event):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    for line in sys.stdin:
        try:
            turn(settings, real, args, json.loads(line), emit)
        except Exception as exc:
            # Do not silently retry or label a failed request a successful answer.
            print('Claude context held: ' + str(exc), file=sys.stderr, flush=True)
            return 1
    return 0


def prepare_legacy(settings, log, cwd):
    """Seed only proven transcript IDs; caller must verify idle and empty native queue first."""
    text = Path(log).read_text(encoding='utf-8', errors='strict')
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    peers = {}
    sender = None
    for line in text.splitlines():
        if re.match(r'● \S+ takes work on Reason Network ', line):
            peers, sender = {}, None  # never revive retired conversations from an earlier listener
            continue
        match = re.match(r'← (\S+) ', line)
        if match:
            sender = re.sub(r'/ask-[0-9a-f]{6}$', '/ask', match[1])
            peers[sender] = None  # latest request must have a transcript, not an older fallback
        elif sender and line.strip().startswith('transcript '):
            value = line.strip()[11:]
            if value.startswith(('~/', '~\\')):
                value = str(Path.home()) + value[1:]
            peers[sender] = Path(value)
    if not peers:
        raise ValueError('No existing conversation evidence; refusing a context-losing restart')
    expected_cwd = os.path.normcase(os.path.abspath(cwd))
    seeds = []
    for peer, transcript in peers.items():
        if not transcript or not transcript.is_file():
            raise ValueError('Missing conversation transcript for ' + peer)
        sid = str(uuid.UUID(transcript.stem))
        seen = False
        for line in transcript.read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            if event.get('type') == 'user' and event.get('sessionId') == sid:
                try:
                    who, _, _ = identity(event)
                except ValueError:
                    continue
                if who != peer:
                    raise ValueError('Transcript sender mismatch')
                # Claude records later cwd changes made by tools; require an anchor at the launch folder.
                if os.path.normcase(os.path.abspath(event.get('cwd', ''))) == expected_cwd:
                    seen = True
        if not seen:
            raise ValueError('Transcript does not prove sender and conversation')
        path = peer_path(settings, peer)
        if path.exists():
            old = read_state(path, peer, expected_cwd)
            if old['pending'] or old['session'] != sid:
                raise ValueError('Existing context journal conflicts with migration')
            continue
        seeds.append((path, {'version': 1, 'peer': peer, 'cwd': expected_cwd, 'session': sid,
                              'started': True, 'pending': None, 'receipts': {}}))
    for path, state in seeds:
        atomic_json(path, state, durable=True)
    return len(peers)
