import os


def bounded(name, default, minimum, maximum):
    value = int(os.environ.get(name, default))
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} is outside its supported range.')
    return value


bind = '0.0.0.0:8000'
worker_class = 'sync'
workers = bounded('GUNICORN_WORKERS', 2, 1, 4)
timeout = bounded('GUNICORN_TIMEOUT_SECONDS', 75, 10, 120)
if timeout <= int(os.environ.get('TULUN_TRANSLATION_TIMEOUT_SECONDS', 60)) + 10:
    raise ValueError('Gunicorn timeout must exceed translation deadline plus 10 seconds.')
graceful_timeout = timeout
keepalive = 2
max_requests = 500
max_requests_jitter = 50
limit_request_line = 2048
limit_request_fields = 32
limit_request_field_size = 4096
accesslog = None
errorlog = '-'
capture_output = False
forwarded_allow_ips = '*'
