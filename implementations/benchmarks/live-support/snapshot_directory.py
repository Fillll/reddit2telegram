"""Read the current public directory for an opt-in, test-channel-only live case."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

import pymongo
import yaml


def snapshot(root, config_path, output):
    if os.environ.get('R2T_LIVE_TESTS') != '1':
        raise ValueError('Explicit local live-test opt-in is required')
    if output.exists():
        raise ValueError('Preserve existing directory snapshots; use a new output path')
    config = yaml.safe_load(config_path.read_text())
    app = config_path.parent.parent
    cron = Path(config['cron_file'])
    if not cron.is_absolute():
        cron = app/cron
    modules = {line.split('\t')[1] for line in cron.read_text().splitlines()[1:]
               if line.strip() and not line.split('\t')[1].startswith('tech_')}
    local = json.loads((root/'implementations/implementations/go/assets/local_channels.json').read_text())
    host = config['db']['host']
    client = pymongo.MongoClient(host if '://' in host else 'mongodb://'+host,
        serverSelectionTimeoutMS=5000, socketTimeoutMS=10000)
    try:
        db = client[config['db']['name']]
        records = list(db.channels.find({'submodule': {'$in': sorted(m.lower() for m in modules)}},
            {'_id': 0, 'submodule': 1, 'channel': 1}, max_time_ms=5000).limit(2001))
        if len(records) >= 2001:
            raise ValueError('Review channel query limit')
        identities = {}
        for row in records:
            if row['submodule'] in identities:
                raise ValueError('Ambiguous channel identity; review duplicate modules')
            identities[row['submodule']] = row.get('channel')
        dates = list(db.settings.find({'kind': 'r2t_anniversary_date'},
            {'_id': 0, 'channel': 1}, max_time_ms=5000).limit(2001))
        if len(dates) >= 2001:
            raise ValueError('Review date-cache query limit')
        cached = {r.get('channel') for r in dates}
        handles = set()
        for module in modules:
            if module == 'r_porn':
                handle = '@r_porn'
            elif module == 'reddit2telegram':
                handle = '@reddit2telegram'
            else:
                handle = identities.get(module.lower(), local.get(module, {}).get('t_channel'))
            if isinstance(handle, str) and re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{4,31}', handle):
                handle = handle.lower()
                if handle in cached and handle not in ('@r_channels', '@r_channels_test'):
                    handles.add(handle)
        channels = sorted(handles-{'@reddit2telegram'})
        if len(channels) < 101:
            raise ValueError('Current directory does not exercise pagination')
        result = dict(captured_utc=datetime.now(timezone.utc).isoformat(), channels=channels,
            active_cached_channels=len(handles), directory_channels=len(channels),
            cron_sha256=hashlib.sha256(cron.read_bytes()).hexdigest(),
            scope='Current configured public handles with persisted anniversary dates; only fixture input, not benchmark traffic or historical comparison. Production state is read-only.')
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
        output.chmod(0o600)
        return {k: result[k] for k in ('captured_utc','active_cached_channels','directory_channels')}
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','config','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.root.resolve(), args.config.resolve(), args.output.resolve()), indent=2))
