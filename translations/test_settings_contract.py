import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class SettingsContractTests(SimpleTestCase):
    def inspect_settings(self, changes, query='import tulun.settings'):
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(('DJANGO_', 'TULUN_', 'AI_GATEWAY_', 'DATABASE_'))
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
