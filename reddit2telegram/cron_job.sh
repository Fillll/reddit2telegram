#! /bin/bash
BASEDIR=$(dirname "$0")
cd $BASEDIR
source ../env/bin/activate
python cron_app.py
