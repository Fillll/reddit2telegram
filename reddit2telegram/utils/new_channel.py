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
        tags_file.write(tags.lower())

    readme_string = '| [/r/{sub_name}](https://www.reddit.com/r/{sub_name}/) | [@{channel_name}](https://t.me/{channel_name}) | 1 hour |'.format(
        sub_name=sub,
        channel_name=channel
    )
    return readme_string


def run_script(channel):
    os.system('python supplier.py --sub ' + channel.lower())


def add_to_git(channel):
    os.system('git add channels/' + channel.lower() + '/*')


def commit(channel):
    os.system('git commit -a -m "@{channel_name}"'.format(channel_name=channel.lower()))


if __name__ == '__main__':
    subreddit_name = input('Subreddit name: ')
    channel_name = input('Channel name: ')
    tags = input('#Tags #in #that #way: ')

    print('Submodule is created.')
    print(main(subreddit_name, channel_name, tags))
    print(channel_name.lower())

    print('Run the bot for the first time.')
    run_script(channel_name)
    print('Done.')

    for i in range(10):
        yes = input('Ready to commit? ')
        if yes == 'y':
            print('Add to git.')
            add_to_git(channel_name)
            print('Done. Will commit.')
            commit(channel_name)
            print('Done.')
            break

