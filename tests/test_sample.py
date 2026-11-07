# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import unittest


class IndependentSource(unittest.TestCase):
    def test_upstream_bytes_are_preserved(self):
        root = Path(__file__).parent / 'fixtures/hello-world'
        provenance = json.loads((root / 'source.json').read_text())
        self.assertEqual(provenance['revision'], '522bcd2faf422c60b9d20e64d7cd6d56600aec97')
        for name, expected in provenance['sha256'].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)
