"""Durable fail-closed journal for native single-message Codex executions."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from storage import atomic_json, file_lock


def request_id(args):
    if not args or 'exec' not in args or '--json' not in args:
        return None
    matches = re.findall(r'<reason-message from="[^"]+" agent="[^"]+" id="([A-Za-z0-9_-]+)">', args[-1])
    if '<reason-message ' in args[-1] and len(matches) != 1:
        raise RuntimeError('Ambiguous Reason request identity; held without executing')
    return matches[0] if matches else None


def safe_to_retry(events):
    """No deployed producer provides an authenticated pre-action admission event."""
    return False


def failure_message(events):
    # Keep both execution paths on the same fail-closed boundary.
    if safe_to_retry(events):
        raise AssertionError('retry policy is not implemented')
    return 'Codex did not produce a verifiable completed answer; held without retry'


def journal_path(settings_path):
    settings = Path(settings_path)
    return settings.parent / 'single-requests' / settings.stem / 'requests.json'


def run(settings_path, real, extra, args):
    mid = request_id(args)
    if mid is None:
        return None
    path = journal_path(settings_path)
    home = path.parent
    with file_lock(home / 'worker.lock', timeout=2):
        journal = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'requests': {}}
        requests = journal['requests']
        previous = requests.get(mid)
        if previous:
            if previous['original'] != args[-1]:
                raise RuntimeError('Request ID conflicts with saved original; held for inspection')
            if previous['status'] != 'completed':
                previous['status'] = 'held'
                atomic_json(path, journal, durable=True)
                raise RuntimeError('Request ' + mid + ' held; inspect saved original and side effects')
            # The previous emission may already have reached Reason. Do not republish.
            raise RuntimeError('Request ' + mid + ' has a cached result; inspect publication before recovery')
        job = {'id': mid, 'original': args[-1], 'status': 'running'}
        requests[mid] = job
        atomic_json(path, journal, durable=True)
        try:
            lines, deferred, events, malformed = [], [], [], False
            with subprocess.Popen([real] + extra + args, stdout=subprocess.PIPE,
                                  text=True, encoding='utf-8', errors='replace') as child:
                for line in child.stdout:
                    lines.append(line)
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError('event is not an object')
                    except ValueError:
                        malformed = True
                        continue
                    events.append(event)
                    item = event.get('item')
                    if item is not None and not isinstance(item, dict):
                        malformed = True
                        continue
                    if (event.get('type') in ('thread.started', 'turn.completed', 'turn.failed', 'error')
                            or (item or {}).get('type') == 'agent_message'):
                        deferred.append(line)
                    else:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                code = child.wait()
            output = ''.join(lines)
            job['partial_output'] = output
            success = (not malformed and code == 0 and any(e.get('type') == 'turn.completed' for e in events)
                       and not any(e.get('type') in ('turn.failed', 'error') for e in events)
                       and any(e.get('type') == 'item.completed' and isinstance(e.get('item'), dict)
                               and e['item'].get('type') == 'agent_message'
                               and isinstance(e['item'].get('text'), str) and e['item']['text'].strip() for e in events))
            if not success:
                raise RuntimeError(failure_message(events))
            job.update(status='completed', output=output)
            job.pop('partial_output', None)
            atomic_json(path, journal, durable=True)
        except BaseException as exc:
            job.update(status='held', error=type(exc).__name__ + ': ' + str(exc))
            atomic_json(path, journal, durable=True)
            raise
        sys.stdout.write(''.join(deferred))
        sys.stdout.flush()
        return 0


def main():
    parser = argparse.ArgumentParser(description='Inspect local single-request recovery records')
    parser.add_argument('action', choices=('status', 'export'))
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--id')
    args = parser.parse_args()
    path = journal_path(args.settings)
    requests = json.loads(path.read_text(encoding='utf-8'))['requests'] if path.exists() else {}
    if args.action == 'export':
        if not args.id or args.id not in requests:
            parser.error('export requires an existing --id')
        result = requests[args.id]
    else:
        result = [{'id': key, 'status': value['status'], 'error': value.get('error')} for key, value in requests.items()]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
