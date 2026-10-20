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

import unittest
from collections import Counter
from pii_fixture import generate_fixture, occurrences, normalized


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.clients = [{'id': n + 1, 'external_id': f'fixture-{n:03}', 'country': country}
                        for n, country in enumerate(['Rwanda'] * 25 + ['Ethiopia'] * 25 +
                                                    ['South Sudan'] * 25 + ['Kenya'] * 25)]

    def test_repeatable_and_independent_of_input_order(self):
        first = generate_fixture(self.clients)
        second = generate_fixture(list(reversed(self.clients)))
        self.assertEqual(first, second)
        self.assertEqual(len({x['identity']['email'] for x in first['clients']}), 100)
        self.assertEqual(Counter(x['profile'] for x in first['clients']), {'regional': 80, 'global': 20})
        self.assertEqual(Counter(x['scenario'] for x in first['loans']),
                         {'on-time': 10, 'late': 10, 'partial': 6, 'approved-undisbursed': 4})
        self.assertEqual(len({x['client_id'] for x in first['loans']}), 30)

    def test_occurrence_spans_and_unexpected_locations(self):
        fixture = generate_fixture(self.clients)
        for client in fixture['clients']:
            identity = client['identity']
            self.assertNotIn('SYNTHETIC', identity['full_name'])
            self.assertTrue(identity['email'].endswith('@example.org'))
            matches = occurrences(client['note'], identity)
            self.assertTrue({'person_name', 'phone', 'email', 'national_id'}.issubset({x['type'] for x in matches}))
            for match in matches:
                self.assertEqual(client['note'][match['start']:match['end']], match['value'])
        self.assertTrue(any(not x['identity']['full_name'].isascii() for x in fixture['clients']))
        self.assertGreaterEqual(len(fixture['file_only_stress_cases']), 5)
        self.assertTrue(all(x['storage'] == 'file-only' for x in fixture['file_only_stress_cases']))

    def test_normalization_handles_obfuscated_contact_variants(self):
        self.assertEqual(normalized(' A\u200bB.C +250 (780) 123-456 '), 'abc250780123456')


if __name__ == '__main__':
    unittest.main()
