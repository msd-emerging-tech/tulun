import contextlib
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from translations.gateway import GatewayError, complete


@override_settings(AI_GATEWAY_MODELS=('translation-test',), AI_GATEWAY_API_KEY='transport-test-key')
class GatewayTransportTests(SimpleTestCase):
    error_prefix = 'GATEWAY'

    def setUp(self):
        self.calls = []
        self.status = 200
        self.body = json.dumps({
            'id': 'mock', 'object': 'chat.completion', 'created': 1,
            'model': 'translation-test', 'choices': [{
                'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': 'Mock translation'},
            }],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
        }).encode()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.calls.append({
                    'path': self.path, 'authorization': self.headers.get('Authorization'),
                    'request_id': self.headers.get('X-Request-ID'),
                    'payload': json.loads(self.rfile.read(int(self.headers['Content-Length']))),
                })
                self.send_response(owner.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(owner.body)))
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.settings_override = override_settings(
            AI_PROVIDER='gateway',
            AI_GATEWAY_BASE_URL=f'http://127.0.0.1:{self.server.server_port}/governed-ai-gateway/v1',
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def invoke(self):
        return complete(
            'translation-test', [{'role': 'user', 'content': 'sensitive-test-text'}],
            time.monotonic() + 10, 'transport-request',
        )

    def test_real_litellm_transport_uses_selected_path_and_separate_key(self):
        self.assertEqual(self.invoke(), 'Mock translation')
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call['path'], '/governed-ai-gateway/v1/chat/completions')
        self.assertEqual(call['authorization'], 'Bearer transport-test-key')
        self.assertEqual(call['request_id'], 'transport-request')
        self.assertEqual(call['payload']['model'], 'translation-test')
        self.assertFalse(call['payload'].get('stream', False))
        self.assertEqual(call['payload']['max_tokens'], 2048)

    def test_transport_failures_do_not_retry_or_print_sensitive_details(self):
        for status, expected_code, expected_status in (
            (401, f'{self.error_prefix}_AUTHENTICATION_FAILED', 502),
            (403, f'{self.error_prefix}_AUTHENTICATION_FAILED', 502),
            (429, f'{self.error_prefix}_RATE_LIMITED', 429),
            (500, f'{self.error_prefix}_UNAVAILABLE', 502),
            (503, f'{self.error_prefix}_UNAVAILABLE', 502),
            (400, f'{self.error_prefix}_POLICY_REJECTED', 422),
        ):
            with self.subTest(status=status):
                self.status = status
                self.body = b'{"error":{"message":"transport-test-key sensitive-test-text","type":"mock_error"}}'
                before = len(self.calls)
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    with self.assertRaises(GatewayError) as raised:
                        self.invoke()
                self.assertEqual(raised.exception.code, expected_code)
                self.assertEqual(raised.exception.status, expected_status)
                self.assertEqual(len(self.calls), before + 1)
                self.assertNotIn('transport-test-key', captured.getvalue())
                self.assertNotIn('sensitive-test-text', captured.getvalue())

    def test_sdk_timeout_mapping(self):
        import litellm
        with patch('litellm.completion', side_effect=litellm.Timeout(
            message='transport-test-key', model='translation-test', llm_provider='openai',
        )), self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.code, f'{self.error_prefix}_TIMEOUT')

    def test_expired_deadline_and_large_context_never_make_request(self):
        with self.assertRaises(GatewayError):
            complete('translation-test', [], time.monotonic() - 1, 'request')
        with self.assertRaises(GatewayError):
            complete('translation-test', [{'role': 'user', 'content': 'a' * 24001}], time.monotonic() + 10, 'request')
        self.assertEqual(self.calls, [])

    def test_missing_or_malformed_success_payload_is_controlled(self):
        self.body = b'{}'
        with self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.status, 502)
        self.assertIn(raised.exception.code, (f'{self.error_prefix}_INVALID_RESPONSE', f'{self.error_prefix}_UNAVAILABLE'))


class FoundryTransportTests(GatewayTransportTests):
    error_prefix = 'FOUNDRY'

    def setUp(self):
        super().setUp()
        self.foundry_override = override_settings(
            AI_PROVIDER='foundry',
            AZURE_FOUNDRY_API_STYLE='chat_completions',
            AZURE_FOUNDRY_BASE_URL=f'http://127.0.0.1:{self.server.server_port}/openai/v1',
            AZURE_FOUNDRY_API_KEY='transport-test-key',
            AZURE_FOUNDRY_MODELS=('translation-test',),
            AI_GATEWAY_API_KEY='unused-gateway-key',
        )
        self.foundry_override.enable()

    def tearDown(self):
        self.foundry_override.disable()
        super().tearDown()

    def test_real_litellm_transport_uses_selected_path_and_separate_key(self):
        self.assertEqual(self.invoke(), 'Mock translation')
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call['path'], '/openai/v1/chat/completions')
        self.assertEqual(call['authorization'], 'Bearer transport-test-key')
        self.assertEqual(call['request_id'], 'transport-request')
        self.assertEqual(call['payload']['model'], 'translation-test')
        self.assertFalse(call['payload'].get('stream', False))
        self.assertEqual(call['payload']['max_tokens'], 2048)

    @override_settings(AZURE_FOUNDRY_API_KEY='')
    def test_missing_foundry_key_never_falls_back_to_gateway(self):
        with self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.code, 'SERVICE_NOT_CONFIGURED')
        self.assertEqual(self.calls, [])

    @override_settings(AZURE_FOUNDRY_MODELS=('other-deployment',))
    def test_gateway_alias_cannot_bypass_foundry_allowlist(self):
        with self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.code, 'CONFIGURATION_NOT_SUPPORTED')
        self.assertEqual(self.calls, [])

    @override_settings(AI_PROVIDER='unknown')
    def test_unknown_provider_never_makes_a_request(self):
        with self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.code, 'SERVICE_NOT_CONFIGURED')
        self.assertEqual(self.calls, [])


class FoundryResponsesTransportTests(FoundryTransportTests):
    def setUp(self):
        super().setUp()
        self.responses_override = override_settings(
            AZURE_FOUNDRY_API_STYLE='responses', AZURE_FOUNDRY_MODELS=('gpt-6-luna',),
        )
        self.responses_override.enable()
        self.response_payload = {
            'id': 'resp_mock', 'object': 'response', 'created_at': 1,
            'model': 'gpt-6-luna', 'status': 'completed',
            'error': None, 'incomplete_details': None,
            'output': [{
                'id': 'msg_mock', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': 'Mock translation', 'annotations': []}],
            }],
        }
        self.body = json.dumps(self.response_payload).encode()

    def tearDown(self):
        self.responses_override.disable()
        super().tearDown()

    def invoke(self):
        return complete(
            'gpt-6-luna', [{'role': 'user', 'content': 'sensitive-test-text'}],
            time.monotonic() + 10, 'transport-request',
        )

    def test_real_litellm_transport_uses_selected_path_and_separate_key(self):
        self.assertEqual(self.invoke(), 'Mock translation')
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call['path'], '/openai/v1/responses')
        self.assertEqual(call['authorization'], 'Bearer transport-test-key')
        self.assertEqual(call['request_id'], 'transport-request')
        self.assertEqual(call['payload']['model'], 'gpt-6-luna')
        self.assertEqual(call['payload']['input'], [{'role': 'user', 'content': 'sensitive-test-text'}])
        self.assertEqual(call['payload']['max_output_tokens'], 2048)
        self.assertIs(call['payload']['store'], False)
        self.assertIs(call['payload']['background'], False)
        self.assertFalse(call['payload'].get('stream', False))
        self.assertNotIn('messages', call['payload'])

    def test_sdk_timeout_mapping(self):
        import litellm
        with patch('litellm.responses', side_effect=litellm.Timeout(
            message='transport-test-key', model='gpt-6-luna', llm_provider='openai',
        )), self.assertRaises(GatewayError) as raised:
            self.invoke()
        self.assertEqual(raised.exception.code, 'FOUNDRY_TIMEOUT')

    def test_expired_deadline_and_large_context_never_make_request(self):
        with self.assertRaises(GatewayError):
            complete('gpt-6-luna', [], time.monotonic() - 1, 'request')
        with self.assertRaises(GatewayError):
            complete('gpt-6-luna', [{'role': 'user', 'content': 'a' * 24001}], time.monotonic() + 10, 'request')
        self.assertEqual(self.calls, [])

    def test_incomplete_and_refused_outputs_are_not_successful_translations(self):
        for update in (
            {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}},
            {'status': 'failed', 'error': {'code': 'server_error', 'message': 'sensitive-test-text'}},
            {'output': []},
            {'output': [{
                'id': 'msg_mock', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'refusal', 'refusal': 'sensitive-test-text'}],
            }]},
            {'output': [{
                'id': 'tool_mock', 'type': 'function_call', 'status': 'completed',
                'call_id': 'call_mock', 'name': 'unexpected', 'arguments': '{}',
            }]},
        ):
            with self.subTest(update=update):
                self.body = json.dumps({**self.response_payload, **update}).encode()
                with self.assertRaises(GatewayError) as raised:
                    self.invoke()
                self.assertEqual(raised.exception.code, 'FOUNDRY_INVALID_RESPONSE')

    def test_reasoning_output_before_text_is_accepted(self):
        self.body = json.dumps({
            **self.response_payload,
            'output': [{'id': 'reasoning_mock', 'type': 'reasoning', 'summary': []}]
                      + self.response_payload['output'],
        }).encode()
        self.assertEqual(self.invoke(), 'Mock translation')
