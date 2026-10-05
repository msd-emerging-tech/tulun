import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen

from mock_gateway import Handler


ROOT = Path(__file__).resolve().parent.parent


def run(command, environment=None, capture=False):
    result = subprocess.run(
        command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=600,
    )
    if result.returncode:
        raise RuntimeError('Command failed; output suppressed to protect runtime secrets.')
    return result.stdout.strip() if capture else None


def wait_for(url):
    for attempt in range(100):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError('Service did not become healthy.')


def request_translation(base, token, configuration_id):
    request = Request(
        f'{base}/api/v1/translate',
        data=json.dumps({
            'text': 'Treat the wound.', 'source_language': 'en',
            'target_language': 'mi', 'configuration_id': configuration_id,
        }).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    )
    with urlopen(request, timeout=90) as response:
        result = json.load(response)
    if result['translation'] != 'Whakaora te patunga.':
        raise RuntimeError('Mocked translation was not returned.')
    return result['translation_id']


def configure(manage, environment=None):
    output = run(manage + [
        'configure_translation', '--target-language-code', 'mi',
        '--target-language-name', 'Māori', '--translation-model', 'translation-test',
        '--post-editing-model', 'translation-test',
    ], environment, capture=True)
    return int(output.rsplit('id=', 1)[1])


def environment(database_url, gateway_url):
    return {
        'TULUN_MODE': 'msd', 'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
        'DJANGO_ALLOWED_HOSTS': '127.0.0.1 localhost', 'DATABASE_URL': database_url,
        'TULUN_API_KEY': secrets.token_urlsafe(32),
        'AI_GATEWAY_BASE_URL': gateway_url, 'AI_GATEWAY_API_KEY': secrets.token_urlsafe(32),
        'AI_GATEWAY_MODELS': 'translation-test', 'AI_GATEWAY_ALLOW_INSECURE_HTTP': 'true',
        'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    }


def native():
    database_url = os.environ.get('TULUN_SMOKE_DATABASE_URL')
    if not database_url:
        raise RuntimeError('Supply TULUN_SMOKE_DATABASE_URL for a dedicated disposable PostgreSQL database.')
    gateway = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    env = {**os.environ, **environment(database_url, f'http://127.0.0.1:{gateway.server_port}/v1')}
    manage = [sys.executable, 'manage.py']
    server = None
    try:
        run(manage + ['migrate', '--noinput'], env)
        print('PASS explicit PostgreSQL migrations')
        configuration_id = configure(manage, env)
        for iteration in range(2):
            server = subprocess.Popen(
                [str(Path(sys.executable).parent / 'gunicorn'), '--config', 'gunicorn.conf.py', 'tulun.wsgi:application'],
                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            wait_for('http://127.0.0.1:8000/api/v1/health')
            if iteration == 0:
                translation_id = request_translation('http://127.0.0.1:8000', env['TULUN_API_KEY'], configuration_id)
                print('PASS Gunicorn health and mocked Gateway translation')
            else:
                verification = (
                    'from translations.models import Translation; '
                    f'assert Translation.objects.get(pk={translation_id}).final_translation == "Whakaora te patunga."'
                )
                run(manage + ['shell', '-c', verification], env)
                print('PASS process restart and PostgreSQL persistence')
            server.terminate()
            server.wait(timeout=90)
            server = None
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=90)
        gateway.shutdown()
        gateway.server_close()
    print('3/3 native runtime checks passed (not container proof)')


def docker():
    suffix = secrets.token_hex(4)
    image = f'tulun-smoke:{suffix}'
    network = f'tulun-smoke-{suffix}'
    names = {role: f'{network}-{role}' for role in ('db', 'gateway', 'api')}
    with tempfile.TemporaryDirectory(prefix='tulun-smoke-') as temporary:
        temporary = Path(temporary)
        password = secrets.token_hex(24)
        env = environment(
            f'postgresql://tulun:{password}@{names["db"]}:5432/tulun',
            f'http://{names["gateway"]}:8000/v1',
        )
        env_file = temporary / 'runtime.env'
        env_file.write_text(''.join(f'{key}={value}\n' for key, value in env.items()))
        env_file.chmod(0o600)
        db_env_file = temporary / 'database.env'
        db_env_file.write_text(f'POSTGRES_USER=tulun\nPOSTGRES_DB=tulun\nPOSTGRES_PASSWORD={password}\n')
        db_env_file.chmod(0o600)
        try:
            run(['docker', 'build', '-t', image, '.'])
            print('PASS Docker build')
            run(['docker', 'network', 'create', network])
            run(['docker', 'run', '-d', '--name', names['db'], '--network', network,
                 '--env-file', str(db_env_file), 'postgres:16.14-bookworm'])
            for attempt in range(100):
                check = subprocess.run(
                    ['docker', 'exec', names['db'], 'pg_isready', '-U', 'tulun'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if check.returncode == 0:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError('PostgreSQL did not become ready.')
            run(['docker', 'run', '-d', '--name', names['gateway'], '--network', network,
                 '--mount', f'type=bind,src={ROOT / "scripts/mock_gateway.py"},dst=/tmp/mock_gateway.py,readonly',
                 '--entrypoint', 'python', image, '/tmp/mock_gateway.py'])
            base_run = ['docker', 'run', '--rm', '--network', network, '--env-file', str(env_file), image]
            manage = base_run + ['python', 'manage.py']
            run(manage + ['migrate', '--noinput'])
            print('PASS image supports explicit migration command')
            configuration_id = configure(manage)
            run(['docker', 'run', '-d', '--name', names['api'], '--network', network,
                 '--env-file', str(env_file), '-p', '127.0.0.1::8000', image])
            published = run(['docker', 'port', names['api'], '8000/tcp'], capture=True)
            base = f'http://{published}'
            wait_for(f'{base}/api/v1/health')
            print('PASS container health')
            translation_id = request_translation(base, env['TULUN_API_KEY'], configuration_id)
            print('PASS translation through mocked Gateway')
            run(['docker', 'rm', '-f', names['api']])
            run(['docker', 'run', '-d', '--name', names['api'], '--network', network,
                 '--env-file', str(env_file), '-p', '127.0.0.1::8000', image])
            published = run(['docker', 'port', names['api'], '8000/tcp'], capture=True)
            wait_for(f'http://{published}/api/v1/health')
            run(manage + ['shell', '-c',
                f'from translations.models import Translation; assert Translation.objects.filter(pk={translation_id}).exists()'])
            print('PASS API container replacement and external database persistence')
            print('5/5 container checks passed')
        finally:
            for name in names.values():
                subprocess.run(['docker', 'rm', '-fv', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['docker', 'network', 'rm', network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['docker', 'image', 'rm', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Token-free isolated runtime verification; never use a production database.')
    parser.add_argument('--docker', action='store_true')
    options = parser.parse_args()
    try:
        docker() if options.docker else native()
    except Exception:
        print('FAIL runtime smoke check; details suppressed to avoid exposing secrets.', file=sys.stderr)
        sys.exit(1)
