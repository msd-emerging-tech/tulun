from pathlib import Path
import re

from django.test import SimpleTestCase


class ContainerContractTests(SimpleTestCase):
    def test_dependency_and_runtime_stages_share_pinned_trixie_base(self):
        dockerfile = (Path(__file__).resolve().parent.parent / 'Dockerfile').read_text()
        stages = re.findall(r'^FROM (\S+) AS (\S+)$', dockerfile, re.MULTILINE)
        self.assertEqual([stage for image, stage in stages], ['dependencies', 'runtime'])
        self.assertEqual(stages[0][0], stages[1][0])
        self.assertRegex(stages[0][0], r'^python:3\.12\.\d+-slim-trixie@sha256:[a-f0-9]{64}$')
