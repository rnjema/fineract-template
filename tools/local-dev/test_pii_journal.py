# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

import importlib.util
from pathlib import Path
import tempfile
import unittest
from collections import Counter

spec = importlib.util.spec_from_file_location('pii_seed', Path(__file__).parent / 'Seed-PIITestbed.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class JournalTests(unittest.TestCase):
    def setUp(self):
        runtime = Path(__file__).parent / '.runtime' / 'test-tmp'
        runtime.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runtime)
        if not Path(self.temp.name).resolve().is_relative_to(runtime.resolve()):
            raise RuntimeError('Test temporary directory escaped workspace')
        self.runner = object.__new__(module.Runner)
        self.runner.journal = {}
        self.runner.journal_path = Path(self.temp.name) / 'journal.json'
        self.runner.stats = Counter()
        self.calls = []
        def api(method, path, body):
            self.calls.append((method, path, body))
            return {'resourceId': 12}
        self.runner.api = api

    def tearDown(self):
        self.temp.cleanup()

    def test_completed_financial_command_is_not_reposted(self):
        for _ in range(2):
            self.assertEqual(self.runner.command('payment', 'POST', '/loans/1/transactions', {'amount': '25'}), {'resourceId': 12})
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(RuntimeError, 'payload changed'):
            self.runner.command('payment', 'POST', '/loans/1/transactions', {'amount': '50'})

    def test_timeout_remains_pending_and_requires_reconciliation(self):
        def timeout(*args):
            raise TimeoutError('No response; outcome unknown')
        self.runner.api = timeout
        with self.assertRaises(TimeoutError):
            self.runner.command('payment', 'POST', '/loans/1/transactions', {'amount': '25'})
        self.assertEqual(self.runner.journal['payment']['state'], 'pending')
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous interrupted'):
            self.runner.command('payment', 'POST', '/loans/1/transactions', {'amount': '25'})


if __name__ == '__main__':
    unittest.main()
