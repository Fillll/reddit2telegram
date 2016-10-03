#! /bin/bash
BASEDIR=$(dirname "$0")
cd $BASEDIR
source env/bin/activate
python main_app.py --sub $1
