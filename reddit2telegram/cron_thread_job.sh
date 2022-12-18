#! /bin/bash
BASEDIR=$(dirname "$0")
cd $BASEDIR
source ../env/bin/activate
python task_queue_cron_app.py
