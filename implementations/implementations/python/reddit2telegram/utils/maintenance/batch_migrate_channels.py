#encoding:utf-8

import os
import re
import yaml
import pymongo

CHANNELS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'channels')


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'prod.yml')
    with open(config_path) as f:
        return yaml.safe_load(f.read())


def list_submodules():
    names = []
    for name in os.listdir(CHANNELS_DIR):
        if name in ('~inactive', '~migrated', '__pycache__'):
            continue
        if name.startswith('tech_'):
            continue
        app_path = os.path.join(CHANNELS_DIR, name, 'app.py')
        if os.path.isfile(app_path):
            names.append(name)
    return sorted(names)


def parse_tags(tags_path):
    if not os.path.exists(tags_path):
        return ''
    with open(tags_path, 'r') as f:
        return f.read().strip()


def ensure_min_tags(tags):
    parts = [p for p in tags.split() if p.startswith('#')]
    if len(parts) >= 3:
        return ' '.join(parts)
    # pad with generic tags
    extras = ['#reddit', '#channel', '#daily']
    for extra in extras:
        if extra not in parts:
            parts.append(extra)
        if len(parts) >= 3:
            break
    return ' '.join(parts)


def parse_module(app_path):
    with open(app_path, 'r') as f:
        code = f.read()

    subreddit_match = re.search(r"subreddit\s*=\s*'([^']+)'", code)
    t_channel_match = re.search(r"t_channel\s*=\s*'([^']+)'", code)
    min_upvotes_match = re.search(r"min_upvotes_limit\s*=\s*([0-9]+)", code)

    content = None
    if 'send_simple' in code:
        content = {
            'text': None,
            'gif': None,
            'video': None,
            'img': None,
            'album': None,
            'gallery': None,
            'other': None
        }
        for key in list(content.keys()):
            m = re.search(r"\b{}\s*=\s*(True|False)".format(key), code)
            if m:
                content[key] = True if m.group(1) == 'True' else False
        # drop if all None
        if all(v is None for v in content.values()):
            content = None
        else:
            # default any unset to True to match DefaultChannel behavior
            for k, v in content.items():
                if v is None:
                    content[k] = True

    subreddit = None
    if subreddit_match:
        subreddit = subreddit_match.group(1)
    elif 'weighted_random_subreddit' in code:
        # collect all subreddit keys
        keys = re.findall(r"'([^']+)'\s*:\s*[0-9\.]", code)
        if keys:
            subreddit = '+'.join(keys)

    t_channel = t_channel_match.group(1) if t_channel_match else None
    min_upvotes = int(min_upvotes_match.group(1)) if min_upvotes_match else None

    return {
        'subreddit': subreddit,
        't_channel': t_channel,
        'min_upvotes_limit': min_upvotes,
        'content': content
    }


def migrate_batch(limit=10):
    config = load_config()
    client = pymongo.MongoClient(host=config['db']['host'])
    db = client[config['db']['name']]
    channels = db['channels']

    migrated_dir = os.path.join(CHANNELS_DIR, '~migrated')
    os.makedirs(migrated_dir, exist_ok=True)

    submodules = list_submodules()[:limit]
    results = []

    for name in submodules:
        app_path = os.path.join(CHANNELS_DIR, name, 'app.py')
        tags_path = os.path.join(CHANNELS_DIR, name, 'tags.txt')
        parsed = parse_module(app_path)
        tags = ensure_min_tags(parse_tags(tags_path))

        doc = {
            'submodule': name,
            'channel': parsed['t_channel'] or '@' + name,
            'subreddit': parsed['subreddit'] or name,
            'tags': tags,
            'min_upvotes_limit': parsed['min_upvotes_limit'],
            'submissions_ranking': 'hot',
            'submissions_limit': 100
        }
        if parsed['content'] is not None:
            doc['content'] = parsed['content']

        channels.update_one({'submodule': name}, {'$setOnInsert': doc}, upsert=True)

        dest = os.path.join(migrated_dir, name)
        os.rename(os.path.join(CHANNELS_DIR, name), dest)
        results.append(doc)

    return results


if __name__ == '__main__':
    batch = migrate_batch()
    for item in batch:
        print('{submodule} -> {channel} | {subreddit}'.format(**item))
