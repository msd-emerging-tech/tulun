import json
import logging
import re
import time
import uuid

from django.conf import settings


logger = logging.getLogger('tulun.api')
API_ROUTES = {'/api/v1/health', '/api/v1/ready', '/api/v1/translate'}


class ApiBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from translations.api import error_response
        started = time.monotonic()
        incoming = request.headers.get('X-Request-ID', '')
        request.request_id = incoming if re.fullmatch(r'[A-Za-z0-9._-]{1,64}', incoming) else str(uuid.uuid4())
        request.error_category = None
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            length = -1
        if request.path in API_ROUTES and length < 0:
            response = error_response(request, 'INVALID_REQUEST', 'Invalid content length.', 400)
        elif request.path in API_ROUTES and length > settings.TULUN_MAX_BODY_BYTES:
            response = error_response(request, 'REQUEST_TOO_LARGE', 'Request body exceeds the limit.', 413)
        else:
            response = self.get_response(request)
        if response.status_code >= 400 and not response.get('Content-Type', '').startswith('application/json'):
            status = response.status_code
            code = {400: 'INVALID_REQUEST', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 413: 'REQUEST_TOO_LARGE'}.get(status, 'INTERNAL_ERROR')
            response = error_response(request, code, 'Request could not be completed.', status)
        response['X-Request-ID'] = request.request_id
        response['Cache-Control'] = 'no-store'
        logger.info(json.dumps({
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'request_id': request.request_id,
            'route': request.path if request.path in API_ROUTES else 'unmatched',
            'status': response.status_code,
            'duration_ms': round((time.monotonic() - started) * 1000),
            'error_category': request.error_category,
        }))
        return response
