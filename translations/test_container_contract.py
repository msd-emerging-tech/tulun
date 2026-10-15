from pathlib import Path
import os
import re
import runpy
from unittest.mock import patch

from django.test import SimpleTestCase


class ContainerContractTests(SimpleTestCase):
    def gunicorn_configuration(self, changes):
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith('GUNICORN_') and key != 'TULUN_TRANSLATION_TIMEOUT_SECONDS'
        }
        environment.update(changes)
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parent.parent / 'gunicorn.conf.py'))

    def test_single_worker_default_for_512_mib_container(self):
        configuration = self.gunicorn_configuration({})
        self.assertEqual(configuration['workers'], 1)
        self.assertEqual(configuration['worker_class'], 'sync')

    def test_explicit_worker_override_is_preserved(self):
        self.assertEqual(self.gunicorn_configuration({'GUNICORN_WORKERS': '2'})['workers'], 2)

    def test_worker_override_remains_bounded(self):
        for value in ('0', '5', 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.gunicorn_configuration({'GUNICORN_WORKERS': value})

    def test_dependency_and_runtime_stages_share_pinned_trixie_base(self):
        dockerfile = (Path(__file__).resolve().parent.parent / 'Dockerfile').read_text()
        stages = re.findall(r'^FROM (\S+) AS (\S+)$', dockerfile, re.MULTILINE)
        self.assertEqual([stage for image, stage in stages], ['dependencies', 'runtime'])
        self.assertEqual(stages[0][0], stages[1][0])
        self.assertRegex(stages[0][0], r'^python:3\.12\.\d+-slim-trixie@sha256:[a-f0-9]{64}$')
