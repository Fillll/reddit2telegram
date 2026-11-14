#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -f "$root/implementations/benchmarks/state/active.json" ]]; then
    exec "${R2T_BENCH_PYTHON:-$root/.venv/bin/python}" "$root/implementations/benchmarks/runner.py" schedule --root "$root"
else
    exec "$root/r2t" scheduler
fi
