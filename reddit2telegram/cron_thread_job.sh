#! /bin/bash
BASEDIR=$(dirname "$0")
cd $BASEDIR
source ../.venv/bin/activate
python task_queue_cron_app.py
