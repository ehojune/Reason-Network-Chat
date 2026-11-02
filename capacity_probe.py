"""Disposable, request-independent Codex capacity probes.

Probe results are candidate selection only, never permission to replay a task.
"""
import json
import os
import subprocess
import tempfile
import time
import hashlib
from pathlib import Path
from storage import atomic_json, file_lock


# Message verified in the 0.166.0-alpha.5.1 protocol source. Unknown versions
# cannot use text to select a fallback.
CAPACITY = {
    'codex-cli 0.166.0-alpha.5.1': {
        'selected model is at capacity. please try a different model.',
    },
}
PROMPT = 'Reply only OK. Do not use tools.'


def classify(version, code, stdout):
    try:
        events = [json.loads(line) for line in stdout.splitlines()]
        if not events or any(not isinstance(e, dict) for e in events):
            return 'unknown'
    except (TypeError, ValueError):
        return 'unknown'
    answers, errors, done = [], [], 0
    for event in events:
        kind = event.get('type')
        if kind in ('thread.started', 'turn.started'):
            continue
        if kind == 'turn.completed':
            done += 1
        elif kind in ('error', 'turn.failed'):
            error = event.get('error', event)
            errors.append(error.get('message', '') if isinstance(error, dict) else '')
        elif kind == 'item.completed' and isinstance(event.get('item'), dict):
            item = event['item']
            if item.get('type') == 'agent_message':
                answers.append(item.get('text'))
            elif item.get('type') != 'error' or not str(item.get('message', '')).startswith('Codex is ignoring '):
                return 'unknown'
        else:
            return 'unknown'
    if code == 0 and done == 1 and answers == ['OK'] and not errors:
        return 'ok'
    allowed = CAPACITY.get(version, set())
    if code != 0 and not done and not answers and errors and all(
            isinstance(s, str) and s.strip().lower() in allowed for s in errors):
        return 'capacity'
    return 'unknown'


def probe(real, version, model, effort, timeout=45, runner=subprocess.run):
    env = {k: v for k, v in os.environ.items()
           if k not in ('CLAUDECODE', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_TOOL_CALL_ID')
           and not k.startswith(('CODEX_SANDBOX', 'CODEX_NETWORK_', 'CODEX_INTERNAL_',
                                 'REASON_NETWORK_', 'TINCAN_'))}
    with tempfile.TemporaryDirectory(prefix='rnc-capacity-') as folder:
        command = [real, '-a', 'never', '-c', 'model_reasoning_effort=' + effort,
                   'exec', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                   '-C', folder, '-m', model, '--json', PROMPT]
        try:
            result = runner(command, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', env=env,
                            cwd=folder, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return 'unknown'
        return classify(version, result.returncode, result.stdout)


def choose(real, version, primary, effort, fallback, record, probe_fn=probe, sleep=time.sleep):
    """Record intent before each probe; only capacity permits another attempt."""
    for index, (model, level) in enumerate(((primary, effort), (primary, effort), fallback)):
        if index == 1:
            sleep(2)
        attempt = {'model': model, 'effort': level, 'state': 'running'}
        record(attempt.copy())
        state = probe_fn(real, version, model, level)
        attempt['state'] = state
        record(attempt.copy())
        if state == 'ok':
            return model, level
        if state != 'capacity':
            raise RuntimeError('Probe uncertain; task not dispatched')
    raise RuntimeError('Probe capacity exhausted; task not dispatched')


def route(settings_path, config, real, extra, args, probe_fn=probe, now=time.time):
    """Choose before dispatch, retaining a durable probe audit and cached selection."""
    if not isinstance(config, dict) or config.get('enabled') is not True:
        return args
    ttl = config.get('ttl', 3600)
    if type(ttl) not in (int, float) or not 0 < ttl <= 3600:
        raise RuntimeError('Invalid capacity probe TTL')
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    try:
        import tomllib
        defaults = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
    except FileNotFoundError:
        defaults = {}
    except (ValueError, OSError) as exc:
        raise RuntimeError('Codex configuration unreadable') from exc
    model, effort = defaults.get('model'), defaults.get('model_reasoning_effort')
    options = list(extra) + list(args[:-1])
    for i, arg in enumerate(options):
        value = options[i + 1] if i + 1 < len(options) else ''
        if arg in ('-m', '--model'):
            model = value
        elif arg.startswith('--model='):
            model = arg.split('=', 1)[1]
        elif arg in ('-c', '--config'):
            key, sep, val = value.partition('=')
            if sep and key.strip() == 'model':
                model = val.strip().strip('"\'')
            if sep and key.strip() == 'model_reasoning_effort':
                effort = val.strip().strip('"\'')
    fallback = (config.get('fallback_model'), config.get('fallback_effort'))
    try:
        catalog = json.loads((home / 'models_cache.json').read_text(encoding='utf-8'))
        available = {m['slug']: {x['effort'] for x in m.get('supported_reasoning_levels', [])}
                     for m in catalog['models'] if m.get('visibility') == 'list'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Codex runtime catalog unavailable') from exc
    if not all(isinstance(x, str) and x for x in (model, effort, *fallback)):
        raise RuntimeError('Probe requires explicit model and effort')
    if effort not in available.get(model, set()) or fallback[1] not in available.get(fallback[0], set()):
        raise RuntimeError('Probe model or effort absent from runtime catalog')
    try:
        version_result = subprocess.run([real, '--version'], capture_output=True, text=True,
                                        encoding='utf-8', timeout=10, check=True)
        version = version_result.stdout.strip()
        if not version:
            raise ValueError('empty version')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError('Codex version unavailable') from exc
    key = [str(Path(real).resolve()), version, model, effort, *fallback]
    digest = hashlib.sha256(json.dumps(key, ensure_ascii=True).encode()).hexdigest()
    directory = Path(settings_path).parent / 'capacity-probes' / Path(settings_path).stem
    path = directory / (digest + '.json')
    with file_lock(directory / (digest + '.lock'), timeout=60):
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'key': key, 'attempts': []}
        if data.get('key') != key:
            raise RuntimeError('Probe cache identity mismatch')
        if data.get('attempts') and data['attempts'][-1].get('state') == 'running':
            raise RuntimeError('Interrupted probe held for inspection')
        selected = data.get('selected')
        timestamp = data.get('selected_at', 0)
        if not (isinstance(selected, list) and len(selected) == 2 and
                isinstance(timestamp, (int, float)) and 0 <= now() - timestamp < ttl):
            data.pop('selected', None)
            def record(attempt):
                if attempt['state'] == 'running':
                    data['attempts'].append(attempt)
                else:
                    data['attempts'][-1] = attempt
                atomic_json(path, data, durable=True)
            selected = choose(real, version, model, effort, fallback, record, probe_fn=probe_fn)
            data.update(selected=list(selected), selected_at=now())
            atomic_json(path, data, durable=True)
        # These final overrides precede only the original prompt, which is untouched.
        return args[:-1] + ['-m', selected[0], '-c', 'model_reasoning_effort=' + selected[1], args[-1]]
