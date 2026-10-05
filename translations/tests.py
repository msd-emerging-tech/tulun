import json
from types import SimpleNamespace
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings

from translations.models import CorpusEntry, GlossaryEntry, SystemConfiguration, Translation


@override_settings(
    TULUN_API_KEY='client-test-secret',
    AI_GATEWAY_BASE_URL='https://gateway.example/v1',
    AI_GATEWAY_API_KEY='gateway-test-secret',
    AI_GATEWAY_MODELS=('translation-test',),
)
class ApiTests(TestCase):
    def setUp(self):
        self.config = SystemConfiguration.objects.create(
            target_language_name='Māori', target_language_code='mi',
            translation_model='translation-test', post_editing_model='translation-test',
            translation_prompt='Post-edit English to Māori using supplied examples.',
        )
        self.payload = {
            'text': 'Treat the wound.', 'source_language': 'en',
            'target_language': 'mi', 'configuration_id': self.config.pk,
        }

    def post(self, payload=None, **kwargs):
        return self.client.post(
            '/api/v1/translate', data=json.dumps(self.payload if payload is None else payload),
            content_type='application/json', HTTP_AUTHORIZATION='Bearer client-test-secret',
            **kwargs,
        )

    @staticmethod
    def completion(text='Whakaora te patunga.'):
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(content=text),
        )])

    def test_health_is_public_and_does_not_use_database_or_gateway(self):
        with patch('django.db.backends.utils.CursorWrapper.execute', side_effect=AssertionError), \
                patch('litellm.completion', side_effect=AssertionError):
            response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_success_reuses_pipeline_and_persists_associations(self):
        glossary = GlossaryEntry.objects.create(english_key='wound', translated_entry='patunga')
        memory = CorpusEntry.objects.create(
            english_text='Treat a wound.', translated_text='Whakaora he patunga.', source='test',
        )
        with patch('litellm.completion', return_value=self.completion()) as completion:
            response = self.post(HTTP_X_REQUEST_ID='correlation-123')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['translation'], 'Whakaora te patunga.')
        self.assertEqual(response['X-Request-ID'], 'correlation-123')
        translation = Translation.objects.get(pk=response.json()['translation_id'])
        self.assertEqual(list(translation.glossary_entries.all()), [glossary])
        self.assertEqual(list(translation.corpus_entries.all()), [memory])
        self.assertIsNone(translation.created_by)
        self.assertGreaterEqual(completion.call_count, 2)
        for call in completion.call_args_list:
            self.assertEqual(call.kwargs['api_base'], 'https://gateway.example/v1')
            self.assertEqual(call.kwargs['api_key'], 'gateway-test-secret')
            self.assertEqual(call.kwargs['model'], 'openai/translation-test')
            self.assertFalse(call.kwargs['stream'])
            self.assertEqual(call.kwargs['num_retries'], 0)
        final_prompt = completion.call_args.kwargs['messages'][-1]['content']
        self.assertIn('wound -> patunga', final_prompt)
        self.assertIn('Treat a wound.', final_prompt)

    def test_authentication_is_separate_and_required(self):
        for key in ('', 'Bearer wrong', 'Bearer gateway-test-secret'):
            with self.subTest(key=key):
                response = self.client.post('/api/v1/translate', HTTP_AUTHORIZATION=key)
                self.assertEqual(response.status_code, 401)

    @override_settings(TULUN_API_KEY='')
    def test_unconfigured_authentication_fails_closed(self):
        self.assertEqual(self.post().status_code, 503)

    def test_validation(self):
        cases = [
            ({}, 400), ({**self.payload, 'text': ''}, 400),
            ({**self.payload, 'text': ' '}, 400), ({**self.payload, 'text': 12}, 400),
            ({**self.payload, 'text': 'a' * 4001}, 413),
            ({**self.payload, 'source_language': 'fr'}, 422),
            ({**self.payload, 'target_language': 'xx'}, 422),
            ({**self.payload, 'configuration_id': 99999}, 404),
            ({**self.payload, 'configuration_id': True}, 400),
            ({**self.payload, 'configuration_id': '1'}, 400),
            ({**self.payload, 'model': 'unapproved'}, 400),
            ([], 400), (None, 400),
        ]
        for payload, status in cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    '/api/v1/translate', data=json.dumps(payload), content_type='application/json',
                    HTTP_AUTHORIZATION='Bearer client-test-secret',
                )
                self.assertEqual(response.status_code, status, response.content)
                self.assertIn('request_id', response.json()['error'])

    def test_malformed_json_and_content_type(self):
        for body, content_type, expected in (
            ('{', 'application/json', 400), ('{}', 'text/plain', 415),
            ('{"text": "one", "text": "two"}', 'application/json', 400),
        ):
            response = self.client.post(
                '/api/v1/translate', data=body, content_type=content_type,
                HTTP_AUTHORIZATION='Bearer client-test-secret',
            )
            self.assertEqual(response.status_code, expected)

    @override_settings(TULUN_MAX_BODY_BYTES=100)
    def test_body_size(self):
        self.assertEqual(self.post().status_code, 413)

    def test_methods_and_non_api_routes_are_not_exposed(self):
        self.assertEqual(self.client.get('/api/v1/translate').status_code, 405)
        self.assertEqual(self.client.post('/api/v1/health').status_code, 405)
        for route in ('/admin/', '/translate/', '/accounts/login/', '/api/corpus-entry/', '/'):
            self.assertEqual(self.client.get(route).status_code, 404)

    def test_database_failure_is_controlled(self):
        with patch('django.db.models.query.QuerySet.get', side_effect=OperationalError('db-password')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('db-password', response.content.decode())

    def test_persistence_failure_rolls_back(self):
        manager_class = type(Translation.objects.create(
            source_text='existing', mt_translation='existing', final_translation='existing',
        ).glossary_entries)
        baseline = Translation.objects.count()
        with patch('litellm.completion', return_value=self.completion()), \
                patch.object(manager_class, 'set', side_effect=OperationalError('db-password')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Translation.objects.count(), baseline)

    def test_gateway_error_mapping_does_not_leak_details(self):
        from translations.gateway import GatewayError
        for code, status in (
            ('GATEWAY_TIMEOUT', 504), ('GATEWAY_AUTHENTICATION_FAILED', 502),
            ('GATEWAY_RATE_LIMITED', 429), ('GATEWAY_UNAVAILABLE', 502),
            ('GATEWAY_INVALID_RESPONSE', 502), ('GATEWAY_POLICY_REJECTED', 422),
        ):
            with self.subTest(code=code), patch('litellm.completion', side_effect=GatewayError(code, status)):
                response = self.post()
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()['error']['code'], code)

    def test_malformed_and_truncated_gateway_responses(self):
        for response in (None, SimpleNamespace(choices=[]), self.completion(''), self.completion(123)):
            with self.subTest(response=response), patch('litellm.completion', return_value=response):
                self.assertEqual(self.post().status_code, 502)
        response = self.completion()
        response.choices[0].finish_reason = 'length'
        with patch('litellm.completion', return_value=response):
            self.assertEqual(self.post().status_code, 502)

    def test_legacy_and_unapproved_models_fail_closed(self):
        for model in ('Google Translate', 'Helsinki-NLP/opus-mt-en-tdt', 'gemini/gemini-2.0-flash'):
            self.config.translation_model = model
            self.config.save()
            with patch('litellm.completion') as completion:
                self.assertEqual(self.post().status_code, 503)
                completion.assert_not_called()

    def test_dspy_state_is_rejected_in_msd_mode(self):
        self.config.dspy_config = {'legacy': 'state'}
        self.config.save()
        self.assertEqual(self.post().status_code, 503)

    def test_config_updates_are_not_cached_across_requests(self):
        with patch('litellm.completion', return_value=self.completion()):
            self.assertEqual(self.post().status_code, 200)
            self.config.target_language_code = 'tet'
            self.config.save()
            self.assertEqual(self.post().status_code, 422)

    def test_readiness_has_no_model_call(self):
        with patch('litellm.completion', side_effect=AssertionError):
            self.assertEqual(self.client.get('/api/v1/ready').status_code, 200)
        with patch('django.db.backends.utils.CursorWrapper.execute', side_effect=OperationalError('secret')):
            response = self.client.get('/api/v1/ready')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.content.decode())

    def test_internal_failure_and_logs_do_not_contain_payload_or_secrets(self):
        with patch('litellm.completion', side_effect=RuntimeError('gateway-test-secret')), \
                self.assertLogs('tulun.api', level='INFO') as captured:
            response = self.post()
        self.assertEqual(response.status_code, 500)
        combined = '\n'.join(captured.output) + response.content.decode()
        for forbidden in ('Treat the wound.', 'gateway-test-secret', 'client-test-secret', 'Authorization'):
            self.assertNotIn(forbidden, combined)

    def test_request_ids_are_sanitized(self):
        response = self.client.get('/api/v1/health', HTTP_X_REQUEST_ID='text with spaces and secret')
        self.assertNotEqual(response['X-Request-ID'], 'text with spaces and secret')

    def test_bearer_api_does_not_depend_on_csrf_or_session_cookies(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        with patch('litellm.completion', return_value=self.completion()):
            response = client.post(
                '/api/v1/translate', data=json.dumps(self.payload),
                content_type='application/json', HTTP_AUTHORIZATION='Bearer client-test-secret',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post('/api/v1/health').status_code, 405)

    def test_invalid_host_is_controlled_and_not_logged(self):
        with self.assertLogs('tulun.api', level='INFO') as captured:
            response = self.client.get('/api/v1/health', HTTP_HOST='untrusted-secret-host.example')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('untrusted-secret-host', '\n'.join(captured.output))
        self.assertEqual(response.json()['error']['code'], 'INVALID_REQUEST')
