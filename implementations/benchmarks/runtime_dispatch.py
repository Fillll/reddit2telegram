"""Exec an explicitly selected benchmark runtime only inside its live window."""
import json
import os
from pathlib import Path
import sys
import time


def main():
    root = Path(__file__).resolve().parents[2]
    role, *extra = sys.argv[1:]
    if role not in ('consumer', 'scheduler'):
        raise ValueError('Expected consumer or scheduler')
    os.environ['R2T_BENCHMARK_DISPATCHED'] = '1'
    state = root / 'implementations/benchmarks/state'
    try:
        active = json.loads((state / 'active.json').read_text())
    except FileNotFoundError:
        active = None
    argv = None
    if active and active['started_at'] <= time.time() < active['deadline']:
        runtime = json.loads((state / 'runtime.json').read_text()) if (state / 'runtime.json').exists() else {}
        argv = runtime.get(role)
        if argv is None and active['label'].startswith('python'):
            app = root / 'implementations/implementations/python/reddit2telegram'
            script = 'task_queue_consumer.py' if role == 'consumer' else 'task_queue_cron_app.py'
            argv = [sys.executable, str(app / script), *extra]
            os.chdir(app)
        elif argv is None and active['label'] != 'go':
            raise ValueError('Explicit benchmark runtime command is required')
    if argv is None:
        argv = [str(root / 'r2t'), role, *extra]
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError('Runtime command must be a nonempty string array')
    os.execv(argv[0], argv)


if __name__ == '__main__':
    main()
