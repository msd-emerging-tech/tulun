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


def validate_configuration(configuration):
    if (not settings.AI_GATEWAY_BASE_URL or not settings.AI_GATEWAY_API_KEY
            or not settings.TULUN_API_KEY or not settings.AI_GATEWAY_MODELS
            or settings.TULUN_API_KEY == settings.AI_GATEWAY_API_KEY):
        raise GatewayError('SERVICE_NOT_CONFIGURED', 503)
    if (configuration.translation_model not in settings.AI_GATEWAY_MODELS
            or configuration.post_editing_model not in settings.AI_GATEWAY_MODELS
            or configuration.dspy_config
            or not 0 <= configuration.num_sentences_retrieved <= settings.TULUN_MAX_RETRIEVED_SENTENCES
            or not configuration.translation_prompt.strip()
            or not configuration.target_language_name.strip()):
        raise GatewayError('CONFIGURATION_NOT_SUPPORTED', 503)


def complete(model, messages, deadline, request_id):
    if model not in settings.AI_GATEWAY_MODELS:
        raise GatewayError('CONFIGURATION_NOT_SUPPORTED', 503)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GatewayError('GATEWAY_TIMEOUT', 504)
    if sum(len(message['content']) for message in messages) > settings.TULUN_MAX_PROMPT_CHARS:
        raise GatewayError('TRANSLATION_CONTEXT_TOO_LARGE', 422)
    try:
        response = litellm.completion(
            model=f'openai/{model}',
            api_base=settings.AI_GATEWAY_BASE_URL,
            api_key=settings.AI_GATEWAY_API_KEY,
            messages=messages,
            stream=False,
            timeout=min(settings.AI_GATEWAY_TIMEOUT_SECONDS, remaining),
            num_retries=0,
            max_retries=0,
            max_tokens=settings.AI_GATEWAY_MAX_OUTPUT_TOKENS,
            extra_headers={'X-Request-ID': request_id},
        )
    except GatewayError:
        raise
    except Exception as error:
        status = getattr(error, 'status_code', None)
        if isinstance(error, litellm.Timeout):
            raise GatewayError('GATEWAY_TIMEOUT', 504) from None
        if status in (401, 403):
            raise GatewayError('GATEWAY_AUTHENTICATION_FAILED', 502) from None
        if status == 429:
            raise GatewayError('GATEWAY_RATE_LIMITED', 429) from None
        if status in (400, 422):
            raise GatewayError('GATEWAY_POLICY_REJECTED', 422) from None
        if status == 200:
            raise GatewayError('GATEWAY_INVALID_RESPONSE', 502) from None
        if status or isinstance(error, litellm.APIConnectionError):
            raise GatewayError('GATEWAY_UNAVAILABLE', 502) from None
        raise
    try:
        choice = response.choices[0]
        content = choice.message.content
        if (not isinstance(content, str) or not content.strip()
                or len(content) > settings.TULUN_MAX_TEXT_LENGTH * 4
                or choice.finish_reason != 'stop'):
            raise ValueError
    except (AttributeError, IndexError, TypeError, ValueError):
        raise GatewayError('GATEWAY_INVALID_RESPONSE', 502) from None
    if time.monotonic() > deadline:
        raise GatewayError('GATEWAY_TIMEOUT', 504)
    return content.strip()
