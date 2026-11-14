"""Runtime selection and installed-service compatibility, without app traffic."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path):
    for name in ('r2t', 'reddit2telegram/task_queue_consumer.py',
                 'reddit2telegram/task_queue_cron_app.py',
                 'implementations/benchmarks/runtime_dispatch.py',
                 'implementations/implementations/python/run'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (tmp_path / 'implementations/implementations/python/reddit2telegram').mkdir()
    binary = tmp_path / 'go binary'
    binary.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                      'print(json.dumps(dict(argv=sys.argv[1:],cwd=os.getcwd())))\n')
    binary.chmod(0o755)
    env = {**os.environ, 'R2T_GO_BINARY': str(binary), 'R2T_BENCH_PYTHON': sys.executable}
    env.pop('R2T_BENCHMARK_DISPATCHED', None)
    return tmp_path, env


@pytest.mark.parametrize('role', ['consumer', 'scheduler'])
def test_default_go_preserves_role_config_and_overrides(checkout, role):
    root, env = checkout
    result = subprocess.run([str(root / 'r2t'), role, '--config', '/custom/config with spaces.yml'],
                            env=env, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data['cwd'] == str(root / 'reddit2telegram')
    assert data['argv'] == [role, '--config', str(root / 'reddit2telegram/configs/prod.yml'),
                            '--config', '/custom/config with spaces.yml']


@pytest.mark.parametrize('script,role', [('task_queue_consumer.py', 'consumer'),
                                        ('task_queue_cron_app.py', 'scheduler')])
def test_existing_python_service_command_execs_go(checkout, script, role):
    root, env = checkout
    result = subprocess.run([sys.executable, str(root / 'reddit2telegram' / script)],
                            env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['argv'][0] == role


def test_missing_go_binary_fails_instead_of_starting_python(checkout):
    root, env = checkout
    env['R2T_GO_BINARY'] = str(root / 'missing')
    result = subprocess.run([str(root / 'r2t'), 'consumer'], env=env, capture_output=True, text=True)
    assert result.returncode == 127
    assert 'Go executable missing' in result.stderr


@pytest.mark.parametrize('script', ['task_queue_consumer.py', 'task_queue_cron_app.py'])
def test_legacy_help_does_not_start_application(checkout, script):
    root, env = checkout
    result = subprocess.run([sys.executable, str(root / 'reddit2telegram' / script), '--help'],
                            env=env, capture_output=True, text=True, check=True)
    assert 'Usage:' in result.stdout
    assert 'argv' not in result.stdout


@pytest.mark.parametrize('args', [['consumer', '--config'], ['scheduler', '--typo'],
                                  ['consumer', '--config', '--describe']])
def test_invalid_arguments_do_not_start_application(checkout, args):
    root, env = checkout
    result = subprocess.run([str(root / 'r2t'), *args], env=env, capture_output=True, text=True)
    assert result.returncode == 64
    assert 'argv' not in result.stdout


def test_metadata_does_not_load_application_config(checkout):
    root, env = checkout
    result = subprocess.run([str(root / 'r2t'), '--describe'], env=env,
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['argv'] == ['--describe']


def test_relative_binary_override_survives_working_directory_change(checkout):
    root, env = checkout
    env['R2T_GO_BINARY'] = './go binary'
    result = subprocess.run([str(root / 'r2t'), 'consumer'], cwd=root, env=env,
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['argv'][0] == 'consumer'


@pytest.mark.parametrize('active', [False, True])
def test_benchmark_override_is_limited_to_active_window(checkout, active):
    root, env = checkout
    state = root / 'implementations/benchmarks/state'
    state.mkdir()
    now = time.time()
    (state / 'active.json').write_text(json.dumps(dict(label='rust', started_at=now-60,
                                                     deadline=now+60 if active else now-1)))
    (state / 'runtime.json').write_text(json.dumps(dict(consumer=[env['R2T_GO_BINARY'], 'selected-rust'])))
    result = subprocess.run([str(root / 'r2t'), 'consumer'], env=env,
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['argv'][0] == ('selected-rust' if active else 'consumer')


def test_python_is_an_explicit_choice_with_its_own_working_directory(checkout):
    root, env = checkout
    env['R2T_PYTHON'] = env['R2T_GO_BINARY']
    result = subprocess.run([str(root / 'implementations/implementations/python/run'), 'scheduler'],
                            env=env, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data['argv'][0] == 'task_queue_cron_app.py'
    assert data['cwd'] == str(root / 'implementations/implementations/python/reddit2telegram')
