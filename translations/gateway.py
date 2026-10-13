import os
import time

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
import litellm
from django.conf import settings


litellm.suppress_debug_info = True
litellm.set_verbose = False


class GatewayError(Exception):
    def __init__(self, code, status):
        self.code = code
        self.status = status
        super().__init__(code)


def provider_configuration():
    if settings.AI_PROVIDER == 'gateway':
        return settings.AI_GATEWAY_BASE_URL, settings.AI_GATEWAY_API_KEY, settings.AI_GATEWAY_MODELS
    if settings.AI_PROVIDER == 'foundry':
        return settings.AZURE_FOUNDRY_BASE_URL, settings.AZURE_FOUNDRY_API_KEY, settings.AZURE_FOUNDRY_MODELS
    raise GatewayError('SERVICE_NOT_CONFIGURED', 503)


def client_authentication_configured():
    return bool(settings.TULUN_API_KEY) and settings.TULUN_API_KEY not in (
        settings.AI_GATEWAY_API_KEY, settings.AZURE_FOUNDRY_API_KEY,
    )


def validate_configuration(configuration):
    base_url, api_key, models = provider_configuration()
    if not base_url or not api_key or not models or not client_authentication_configured():
        raise GatewayError('SERVICE_NOT_CONFIGURED', 503)
    if (configuration.translation_model not in models
            or configuration.post_editing_model not in models
            or configuration.dspy_config
            or not 0 <= configuration.num_sentences_retrieved <= settings.TULUN_MAX_RETRIEVED_SENTENCES
            or not configuration.translation_prompt.strip()
            or not configuration.target_language_name.strip()):
        raise GatewayError('CONFIGURATION_NOT_SUPPORTED', 503)


def complete(model, messages, deadline, request_id):
    base_url, api_key, models = provider_configuration()
    if not base_url or not api_key:
        raise GatewayError('SERVICE_NOT_CONFIGURED', 503)
    if model not in models:
        raise GatewayError('CONFIGURATION_NOT_SUPPORTED', 503)
    use_responses = settings.AI_PROVIDER == 'foundry' and settings.AZURE_FOUNDRY_API_STYLE == 'responses'
    error_prefix = 'FOUNDRY' if settings.AI_PROVIDER == 'foundry' else 'GATEWAY'
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GatewayError(f'{error_prefix}_TIMEOUT', 504)
    if sum(len(message['content']) for message in messages) > settings.TULUN_MAX_PROMPT_CHARS:
        raise GatewayError('TRANSLATION_CONTEXT_TOO_LARGE', 422)
    try:
        parameters = {
            'model': f'openai/{model}',
            'api_base': base_url,
            'api_key': api_key,
            'stream': False,
            'timeout': min(settings.AI_GATEWAY_TIMEOUT_SECONDS, remaining),
            'num_retries': 0,
            'max_retries': 0,
            'extra_headers': {'X-Request-ID': request_id},
        }
        if use_responses:
            response = litellm.responses(
                **parameters, input=messages, store=False, background=False,
                max_output_tokens=settings.AI_GATEWAY_MAX_OUTPUT_TOKENS,
            )
        else:
            response = litellm.completion(
                **parameters, messages=messages,
                max_tokens=settings.AI_GATEWAY_MAX_OUTPUT_TOKENS,
            )
    except GatewayError:
        raise
    except Exception as error:
        status = getattr(error, 'status_code', None)
        if isinstance(error, litellm.Timeout):
            raise GatewayError(f'{error_prefix}_TIMEOUT', 504) from None
        if status in (401, 403):
            raise GatewayError(f'{error_prefix}_AUTHENTICATION_FAILED', 502) from None
        if status == 429:
            raise GatewayError(f'{error_prefix}_RATE_LIMITED', 429) from None
        if status in (400, 422):
            raise GatewayError(f'{error_prefix}_POLICY_REJECTED', 422) from None
        if status == 200:
            raise GatewayError(f'{error_prefix}_INVALID_RESPONSE', 502) from None
        if status or isinstance(error, litellm.APIConnectionError):
            raise GatewayError(f'{error_prefix}_UNAVAILABLE', 502) from None
        raise
    try:
        if use_responses:
            if response.status != 'completed' or response.error or response.incomplete_details:
                raise ValueError
            for item in response.model_dump()['output']:
                if item['type'] == 'reasoning':
                    continue
                if item['type'] != 'message' or item['status'] != 'completed' or item['role'] != 'assistant':
                    raise ValueError
                if any(part['type'] != 'output_text' for part in item['content']):
                    raise ValueError
            content = response.output_text
        else:
            choice = response.choices[0]
            if choice.finish_reason != 'stop':
                raise ValueError
            content = choice.message.content
        if (not isinstance(content, str) or not content.strip()
                or len(content) > settings.TULUN_MAX_TEXT_LENGTH * 4):
            raise ValueError
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        raise GatewayError(f'{error_prefix}_INVALID_RESPONSE', 502) from None
    if time.monotonic() > deadline:
        raise GatewayError(f'{error_prefix}_TIMEOUT', 504)
    return content.strip()
