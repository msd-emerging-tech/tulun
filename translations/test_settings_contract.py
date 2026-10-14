import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class SettingsContractTests(SimpleTestCase):
    def inspect_settings(self, changes, query='import tulun.settings'):
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(('DJANGO_', 'TULUN_', 'AI_GATEWAY_', 'AZURE_FOUNDRY_', 'DATABASE_'))
            and key != 'AI_PROVIDER'
        }
        environment.update({
            'TULUN_MODE': 'msd',
            'DJANGO_SECRET_KEY': 'isolated-contract-test-abcdefghijklmnopqrstuvwxyz-1234567890',
            'DJANGO_ALLOWED_HOSTS': 'localhost',
            'DATABASE_URL': 'postgresql://user:contract-db-secret@localhost/tulun',
        })
        environment.update(changes)
        return subprocess.run(
            [sys.executable, '-c', query], env=environment,
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=10,
        )

    def test_postgres_url_without_options_works(self):
        result = self.inspect_settings({},
            'from tulun.settings import DATABASES; '
            'assert DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"; '
            'assert DATABASES["default"]["OPTIONS"]["connect_timeout"] == 5')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsafe_production_settings_fail_without_secret_echo(self):
        for changes in (
            {'DJANGO_SECRET_KEY': ''}, {'DATABASE_URL': ''},
            {'DATABASE_URL': 'sqlite:///contract-db-secret'},
            {'DATABASE_URL': 'postgresql://user:contract-db-secret@localhost:bad/db'},
            {'DJANGO_ALLOWED_HOSTS': '*'}, {'TULUN_MODE': 'production-typo'},
            {'TULUN_MAX_TEXT_LENGTH': '99999999'},
            {'TULUN_API_KEY': 'identical-secret', 'AI_GATEWAY_API_KEY': 'identical-secret'},
            {'AI_GATEWAY_BASE_URL': 'http://gateway.example/v1'},
            {'AI_GATEWAY_BASE_URL': 'https://user:identical-secret@gateway.example/v1'},
            {'AI_PROVIDER': 'provider-typo'},
            {'AZURE_FOUNDRY_BASE_URL': 'http://resource.services.ai.azure.com/openai/v1'},
            {'AZURE_FOUNDRY_BASE_URL': 'https://user:identical-secret@resource.services.ai.azure.com'},
            {'AZURE_FOUNDRY_BASE_URL': 'https://resource.services.ai.azure.com/models'},
            {'AZURE_FOUNDRY_BASE_URL': 'https://resource.services.ai.azure.com/openai/v1?api-version=preview'},
            {'AZURE_FOUNDRY_BASE_URL': 'https://resource.services.ai.azure.com/openai/v1#fragment'},
            {'AZURE_FOUNDRY_API_STYLE': 'unsupported'},
            {'AZURE_FOUNDRY_BASE_URL': 'https://resource.services.ai.azure.com/openai/v1/responses',
             'AZURE_FOUNDRY_API_STYLE': 'chat_completions'},
            {'TULUN_API_KEY': 'identical-secret', 'AZURE_FOUNDRY_API_KEY': 'identical-secret'},
        ):
            with self.subTest(changes=changes):
                result = self.inspect_settings(changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('contract-db-secret', result.stderr)
                self.assertNotIn('identical-secret', result.stderr)

    def test_api_only_mode_cannot_enable_debug_or_legacy_ui(self):
        result = self.inspect_settings(
            {'DJANGO_DEBUG': 'true', 'TULUN_ENABLE_LEGACY_UI': 'true'},
            'from tulun.settings import DEBUG, TULUN_ENABLE_LEGACY_UI; '
            'assert not DEBUG and not TULUN_ENABLE_LEGACY_UI',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_liveness_can_start_without_gateway_credentials(self):
        result = self.inspect_settings({},
            'from tulun.settings import AI_GATEWAY_BASE_URL, AI_GATEWAY_API_KEY; '
            'assert not AI_GATEWAY_BASE_URL and not AI_GATEWAY_API_KEY')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_foundry_resource_url_is_normalized_to_v1(self):
        for endpoint in (
            'https://resource.services.ai.azure.com',
            'https://resource.services.ai.azure.com/',
            'https://resource.services.ai.azure.com/openai/v1/',
        ):
            with self.subTest(endpoint=endpoint):
                result = self.inspect_settings(
                    {'AI_PROVIDER': 'foundry', 'AZURE_FOUNDRY_BASE_URL': endpoint},
                    'from tulun.settings import AI_PROVIDER, AZURE_FOUNDRY_BASE_URL; '
                    'assert AI_PROVIDER == "foundry"; '
                    'assert AZURE_FOUNDRY_BASE_URL == "https://resource.services.ai.azure.com/openai/v1"',
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_responses_endpoint_selects_responses_and_normalizes_base(self):
        for suffix in ('/responses', '/responses/'):
            with self.subTest(suffix=suffix):
                result = self.inspect_settings(
                    {'AI_PROVIDER': 'foundry', 'AZURE_FOUNDRY_BASE_URL':
                     f'https://claude-sonnet-resource.services.ai.azure.com/openai/v1{suffix}'},
                    'from tulun.settings import AZURE_FOUNDRY_BASE_URL, AZURE_FOUNDRY_API_STYLE; '
                    'assert AZURE_FOUNDRY_BASE_URL == "https://claude-sonnet-resource.services.ai.azure.com/openai/v1"; '
                    'assert AZURE_FOUNDRY_API_STYLE == "responses"',
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_foundry_ignores_inactive_gateway_url(self):
        result = self.inspect_settings(
            {
                'AI_PROVIDER': 'foundry',
                'AI_GATEWAY_BASE_URL': 'https://claude-sonnet-resource.services.ai.azure.com/openai/v1/responses',
                'AZURE_FOUNDRY_BASE_URL': 'https://claude-sonnet-resource.services.ai.azure.com/openai/v1/responses',
                'AZURE_FOUNDRY_API_STYLE': 'responses',
                'AZURE_FOUNDRY_MODELS': 'gpt-6-luna',
            },
            'from tulun.settings import AI_PROVIDER, AZURE_FOUNDRY_BASE_URL, '
            'AZURE_FOUNDRY_API_STYLE, AZURE_FOUNDRY_MODELS; '
            'assert AI_PROVIDER == "foundry"; '
            'assert AZURE_FOUNDRY_BASE_URL == "https://claude-sonnet-resource.services.ai.azure.com/openai/v1"; '
            'assert AZURE_FOUNDRY_API_STYLE == "responses"; '
            'assert AZURE_FOUNDRY_MODELS == ("gpt-6-luna",)',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_active_gateway_still_rejects_responses_url(self):
        result = self.inspect_settings({
            'AI_PROVIDER': 'gateway',
            'AI_GATEWAY_BASE_URL': 'https://claude-sonnet-resource.services.ai.azure.com/openai/v1/responses',
        })
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AI_GATEWAY_BASE_URL must be an approved URL ending in /v1.', result.stderr)
        self.assertNotIn('contract-db-secret', result.stderr)

    def test_example_uses_supplied_endpoint_and_exact_deployment(self):
        from dotenv import dotenv_values
        example = dotenv_values(Path(__file__).resolve().parent.parent / '.env.example')
        result = self.inspect_settings(
            {key: value for key, value in example.items() if key.startswith(('AI_', 'AZURE_FOUNDRY_'))},
            'from tulun.settings import AI_PROVIDER, AZURE_FOUNDRY_BASE_URL, '
            'AZURE_FOUNDRY_API_STYLE, AZURE_FOUNDRY_MODELS, AZURE_FOUNDRY_API_KEY; '
            'assert AI_PROVIDER == "foundry"; '
            'assert AZURE_FOUNDRY_BASE_URL == "https://claude-sonnet-resource.services.ai.azure.com/openai/v1"; '
            'assert AZURE_FOUNDRY_API_STYLE == "responses"; '
            'assert AZURE_FOUNDRY_MODELS == ("gpt-6-luna",); '
            'assert not AZURE_FOUNDRY_API_KEY',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
