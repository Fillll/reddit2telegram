"""Exec the selected implementation before loading Python application libraries."""

import json
import os
from pathlib import Path


def dispatch(role):
    if os.environ.get('R2T_RUNTIME_DISPATCHED') == '1':
        return
    control = Path(__file__).resolve().parent.parent / 'implementations/benchmarks/state/runtime.json'
    try:
        runtime = json.loads(control.read_text())
    except FileNotFoundError:
        return
    argv = runtime.get(role)
    if argv is None:
        return
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError('Runtime command must be a nonempty string array')
    os.environ['R2T_RUNTIME_DISPATCHED'] = '1'
    os.execv(argv[0], argv)
