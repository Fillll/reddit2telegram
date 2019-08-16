#encoding:utf-8

import os


def main(sub, channel, tags):
    channel_dir = os.path.join('channels', channel.lower())
    if os.path.isdir(channel_dir):
        print('Directory already exists.')
        return
    os.makedirs(channel_dir)
    with open(os.path.join(channel_dir, '__init__.py'), 'w'):
        pass
    with open(os.path.join(channel_dir, 'app.py'), 'w') as app_file:
        app_file.write('''#encoding:utf-8

subreddit = '{sub_name}'
t_channel = '@{channel_name}'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
'''.format(sub_name=sub, channel_name=channel))

    with open(os.path.join(channel_dir, 'tags.txt'), 'w') as tags_file:
        tags_file.write('#' + ' #'.join(tags.lower().split('_')))

    readme_string = '| [/r/{sub_name}](https://www.reddit.com/r/{sub_name}/) | [@{channel_name}](https://t.me/{channel_name}) | 1 hour |'.format(
        sub_name=sub,
        channel_name=channel
    )
    return readme_string


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--sub')
    parser.add_argument('--channel')
    parser.add_argument('--tags')
    args = parser.parse_args()
    print(main(args.sub, args.channel, args.tags))
