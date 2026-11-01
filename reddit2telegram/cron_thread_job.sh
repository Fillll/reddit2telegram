#! /bin/bash
BASEDIR=$(dirname "$0")
cd $BASEDIR
source ../.venv/bin/activate
if [ -f ../implementations/benchmarks/state/active.json ]; then
    python ../implementations/benchmarks/runner.py schedule --root ..
else
    python task_queue_cron_app.py
fi
