#!/usr/bin/env python3
"""Read-only anniversary inventory, message preview, and retained run history."""

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pymongo
import yaml


APP_DIR = Path(__file__).resolve().parent.parent / 'reddit2telegram'
sys.path.insert(0, str(APP_DIR))
from utils.anniversaries import AnniversaryAnnouncements, RUN_KIND, EVENT_KIND
from utils.anniversaries import anniversary_age, announcement_messages
from utils.anniversaries import utc_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=APP_DIR / 'configs/prod.yml')
    parser.add_argument('--date', type=date.fromisoformat, default=utc_now().date())
    parser.add_argument('--days', type=int, default=7, help='Retained run history, including today')
    args = parser.parse_args()
    if args.days < 1:
        parser.error('--days must be positive')
    with args.config.open() as config_file:
        config = yaml.safe_load(config_file)
    os.chdir(APP_DIR)
    with pymongo.MongoClient(config['db']['host'], serverSelectionTimeoutMS=5000) as client:
        db = client[config['db']['name']]
        service = AnniversaryAnnouncements(SimpleNamespace(
            settings=db.settings, urls=db.urls, config=config,
        ))
        channels, skipped, errors = service.inventory(persist=False)
        due = [{'channel': channel, 'birthday': birthday.isoformat(),
                'years': anniversary_age(birthday, args.date)}
               for channel, birthday in sorted(channels.items())
               if anniversary_age(birthday, args.date) is not None]
        cutoff = datetime.combine(utc_now().date() - timedelta(days=args.days - 1),
                                  datetime.min.time())
        runs = list(db.settings.find(
            {'kind': RUN_KIND, 'started_at': {'$gte': cutoff}},
        ).sort('started_at', -1))
        pending = []
        for event in db.settings.find({'kind': EVENT_KIND, 'complete': False}).batch_size(25):
            pending.append({'id': event['_id'], 'channel': event['channel'],
                            'anniversary': event['anniversary'],
                            'parts': [{'index': i, 'destination': part['destination'],
                                       'state': part['state'], 'message_ids': part.get('message_ids', [])}
                                      for i, part in enumerate(event['deliveries'])]})
        example = due[0] if due else {'channel': '@example_channel', 'years': 1}
        print(json.dumps({
            'read_only': True, 'date': args.date.isoformat(), 'channels': len(channels),
            'skipped_no_history': skipped, 'errors': errors, 'due': due, 'runs': runs,
            'pending': pending,
            'preview': announcement_messages(example['channel'], example['years'], channels, args.date),
        }, ensure_ascii=False, default=str, indent=2))


if __name__ == '__main__':
    main()
