from glob import glob
import os

from utils import channels_stuff


def main():
    submodules_moved = list()
    for submodule_path in glob('channels/*/'):
        submodule_name = submodule_path.split('/')[1].lower()
        print(submodule_name)
        print('=' * 10)
        if submodule_name in ('~inactive', '__pycache__'):
            continue
        if not os.path.isfile(os.path.join(submodule_path, 'app.py')):
            continue
        with open(os.path.join(submodule_path, 'app.py'), 'r') as f:
            code = f.read()
        number_of_lines = code.count('\n')
        if number_of_lines != 8:
            continue
        print(code)
        print('=' * 10)
        print(number_of_lines)
        print('=' * 10)
        to_be_moved = False
        if code.endswith('    return r2t.send_simple(submission)\n'):
            to_be_moved = True
        # to_be_moved = input('Move? [y]/n: ')
        # to_be_moved = True if to_be_moved == 'y' else to_be_moved
        if to_be_moved == 'STOP':
            break
        if to_be_moved == True:
            submodules_moved.append(submodule_name)
            submodule = channels_stuff.import_submodule(submodule_name)
            tags = ''
            if os.path.isfile(os.path.join(submodule_path, 'tags.txt')):
                with open(os.path.join(submodule_path, 'tags.txt'), 'r') as f:
                    tags = f.read()
            print(tags)
            channels_stuff.set_new_channel(submodule.t_channel,
                tags=tags,
                subreddit=submodule.subreddit
            )
            os.system(f'git mv channels/{submodule_name} channels/~inactive/{submodule_name}')
        print('=' * 10)
        print()
        print('=' * 10)

    print(submodules_moved)


def remove_dead_submodules():
    submodules_moved = list()
    for submodule_path in glob('~/reddit2telegram/reddit2telegram/channels/*/'):
        print(submodule_path)
        submodule_name = submodule_path.split('/')[-2].lower()
        print(submodule_name)
        print('=' * 10)
        if submodule_name in ('~inactive', '__pycache__'):
            continue
        if not os.path.isfile(os.path.join(submodule_path, 'app.py')):
            print(submodule_name)
            # input()
            os.system(f'rm -rf {submodule_path}')

if __name__ == '__main__':
    main()
