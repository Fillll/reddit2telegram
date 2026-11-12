"""Stage a test-only Go package; never edit the production package in place."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def stage(root, destination):
    source = root / 'implementations/implementations/go'
    if destination.exists():
        raise ValueError('Destination must be new')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('dist', '*_test.go'))
    changes = {
        'anniversaries.go': [
            ('const mainChannel = "@reddit2telegram"', 'const mainChannel = "@r_channels_test"'),
            ('const community = "@r_channels"', 'const community = "@r_channels_test"'),
        ],
        'http.go': [(
            'func (h *Http) api(token, method string, params D, video string) (any, error) {',
            'func (h *Http) api(token, method string, params D, video string) (any, error) {\n'
            '\tif e := liveRequestGuard(method, params, video); e != nil { return nil, e }',
        )],
    }
    receipt = {'source_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
               'scope': 'Test-only routing and outbound guard; production source and binary untouched',
               'original_package_sha256': {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted(source.rglob('*')) if p.is_file() and 'dist' not in p.relative_to(source).parts},
               'files': {}}
    for name, replacements in changes.items():
        original = (source / name).read_bytes()
        text = original.decode()
        for before, after in replacements:
            if text.count(before) != 1:
                raise ValueError('Unexpected source shape: ' + name)
            text = text.replace(before, after)
        (destination / name).write_text(text)
        receipt['files'][name] = {'original_sha256': hashlib.sha256(original).hexdigest(),
                                  'staged_sha256': hashlib.sha256(text.encode()).hexdigest(),
                                  'replacement_count': len(replacements)}
    shutil.copyfile(Path(__file__).with_name('support_live_test.go'), destination / 'support_live_test.go')
    (destination / 'routing-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    stage(args.root.resolve(), args.destination.resolve())
