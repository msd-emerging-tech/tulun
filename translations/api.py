import hmac
import json
import time

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .gateway import GatewayError, validate_configuration
from .models import CorpusEntry, GlossaryEntry, SystemConfiguration, Translation


def error_response(request, code, message, status):
    request.error_category = code
    response = JsonResponse({'error': {
        'code': code, 'message': message, 'request_id': request.request_id,
    }}, status=status)
    if status == 401:
        response['WWW-Authenticate'] = 'Bearer'
    if code == 'GATEWAY_RATE_LIMITED':
        response['Retry-After'] = '60'
    return response


def check_method(request, method):
    if request.method != method:
        response = error_response(request, 'METHOD_NOT_ALLOWED', 'Method not allowed.', 405)
        response['Allow'] = method
        return response


@csrf_exempt
def health(request):
    return check_method(request, 'GET') or JsonResponse({'status': 'ok'})


@csrf_exempt
def ready(request):
    method_error = check_method(request, 'GET')
    if method_error:
        return method_error
    if (not settings.TULUN_API_KEY or not settings.AI_GATEWAY_BASE_URL
            or not settings.AI_GATEWAY_API_KEY or not settings.AI_GATEWAY_MODELS
            or settings.TULUN_API_KEY == settings.AI_GATEWAY_API_KEY):
        return error_response(request, 'NOT_READY', 'Service is not ready.', 503)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        configuration = SystemConfiguration.objects.first()
        if configuration is None:
            return error_response(request, 'NOT_READY', 'Service is not ready.', 503)
        validate_configuration(configuration)
    except (DatabaseError, GatewayError):
        return error_response(request, 'NOT_READY', 'Service is not ready.', 503)
    return JsonResponse({'status': 'ready'})


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


@csrf_exempt
def translate(request):
    method_error = check_method(request, 'POST')
    if method_error:
        return method_error
    if not settings.TULUN_API_KEY or settings.TULUN_API_KEY == settings.AI_GATEWAY_API_KEY:
        return error_response(request, 'SERVICE_NOT_CONFIGURED', 'Service is not configured.', 503)
    authorization = request.headers.get('Authorization', '')
    expected = f'Bearer {settings.TULUN_API_KEY}'
    if not hmac.compare_digest(authorization.encode('utf-8'), expected.encode('utf-8')):
        return error_response(request, 'UNAUTHORIZED', 'Valid API authentication is required.', 401)
    if request.content_type != 'application/json':
        return error_response(request, 'UNSUPPORTED_MEDIA_TYPE', 'Use application/json.', 415)
    body = request.read(settings.TULUN_MAX_BODY_BYTES + 1)
    if len(body) > settings.TULUN_MAX_BODY_BYTES:
        return error_response(request, 'REQUEST_TOO_LARGE', 'Request body exceeds the limit.', 413)
    try:
        payload = json.loads(body.decode('utf-8'), object_pairs_hook=unique_object)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return error_response(request, 'INVALID_JSON', 'Body must be valid UTF-8 JSON.', 400)
    required = {'text', 'source_language', 'target_language', 'configuration_id'}
    if not isinstance(payload, dict) or set(payload) != required:
        return error_response(request, 'INVALID_REQUEST', 'Provide exactly the documented fields.', 400)
    if (any(not isinstance(payload[field], str) or not payload[field].strip()
            for field in ('text', 'source_language', 'target_language'))
            or type(payload['configuration_id']) is not int
            or not 0 < payload['configuration_id'] <= 9223372036854775807):
        return error_response(request, 'INVALID_REQUEST', 'Invalid field type or empty value.', 400)
    if len(payload['text']) > settings.TULUN_MAX_TEXT_LENGTH:
        return error_response(request, 'TEXT_TOO_LARGE', 'Translation text exceeds the limit.', 413)
    if payload['source_language'] != 'en':
        return error_response(request, 'UNSUPPORTED_LANGUAGE', 'Only English source text is supported.', 422)
    deadline = time.monotonic() + settings.TULUN_TRANSLATION_TIMEOUT_SECONDS
    try:
        configuration = SystemConfiguration.objects.get(pk=payload['configuration_id'])
        if payload['target_language'] != configuration.target_language_code:
            return error_response(request, 'UNSUPPORTED_LANGUAGE', 'Target must match the selected configuration.', 422)
        validate_configuration(configuration)
        from .utils import TranslatorGateway
        translator = TranslatorGateway(configuration, deadline, request.request_id)
        glossary = GlossaryEntry.get_entries(payload['text'])
        memory = CorpusEntry.get_top_similar_bm25(payload['text'], configuration.num_sentences_retrieved)
        machine_translation = translator.translate(payload['text'])
        result = async_to_sync(translator.get_post_edited_translation)(payload['text'], memory, glossary)
        with transaction.atomic():
            translation = Translation.objects.create(
                source_text=payload['text'], mt_translation=machine_translation,
                final_translation=result['final_translation'], created_by=None,
            )
            translation.glossary_entries.set(glossary)
            translation.corpus_entries.set(memory)
        return JsonResponse({
            'translation': translation.final_translation,
            'source_language': 'en', 'target_language': configuration.target_language_code,
            'configuration_id': configuration.pk, 'translation_id': translation.pk,
        })
    except SystemConfiguration.DoesNotExist:
        return error_response(request, 'CONFIGURATION_NOT_FOUND', 'Translation configuration was not found.', 404)
    except DatabaseError:
        return error_response(request, 'DATABASE_UNAVAILABLE', 'Translation storage is unavailable.', 503)
    except GatewayError as error:
        return error_response(request, error.code, 'Translation could not be completed.', error.status)
    except Exception:
        return error_response(request, 'INTERNAL_ERROR', 'Translation could not be completed.', 500)
