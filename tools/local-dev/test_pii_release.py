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
from pii_release import evaluate


class ReleaseTests(unittest.TestCase):
    def test_detects_misplaced_and_formatted_identifiers(self):
        key = {'occurrences': [{'type': 'person_name', 'value': 'Aline Uwimana', 'canonical': 'Aline Uwimana'},
                               {'type': 'phone', 'value': '+250 780-123456', 'canonical': '+250780123456'}],
               'financial_controls': []}
        result = evaluate({'description': 'ALINE UWIMANA: +250 (780) 123456'}, key)
        self.assertFalse(result['known_planted_identifiers_absent'])
        self.assertEqual(result['unique_identifiers_found'], 2)

    def test_control_retention_and_unevaluated_limits(self):
        key = {'occurrences': [{'type': 'email', 'value': 'abc@example.org', 'canonical': 'abc@example.org'}],
               'financial_controls': [{'external_id': 'fixture-loan-001', 'principal': '600.00'}]}
        result = evaluate({'loans': [{'externalId': 'fixture-loan-001', 'principal': 600}]}, key)
        self.assertTrue(result['known_planted_identifiers_absent'])
        self.assertEqual(result['financial_controls_matched'], 1)
        self.assertEqual(result['linkage_consistency'], 'not evaluated')
        self.assertFalse(result['privacy_certified'])
        dropped = evaluate({}, key)
        self.assertEqual(dropped['financial_controls_unjoinable'], 1)
        self.assertEqual(dropped['financial_controls_changed'], 0)

    def test_numeric_phone_and_private_financial_mapping(self):
        key = {'occurrences': [{'type': 'phone', 'value': '+250780123456', 'canonical': '+250780123456'}],
               'financial_controls': [{'external_id': 'fixture-loan-001', 'principal': '600.00'}]}
        release = {'mobileNo': 250780123456, 'loans': [{'externalId': 'token-abc', 'principal': 600}]}
        result = evaluate(release, key, {'fixture-loan-001': 'token-abc'})
        self.assertEqual(result['found_by_type'], {'phone': 1})
        self.assertEqual(result['financial_controls_matched'], 1)
        self.assertEqual(result['financial_controls_unjoinable'], 0)
        self.assertEqual(result['clean_text_false_removals'], 'not evaluated')

    def test_native_date_array_is_checked_without_cross_field_matches(self):
        key = {'occurrences': [{'type': 'date_of_birth', 'value': '1985-02-03', 'canonical': '1985-02-03'},
                               {'type': 'person_name', 'value': 'Aline Uwimana', 'canonical': 'Aline Uwimana'}]}
        result = evaluate({'dateOfBirth': [1985, 2, 3], 'separate': ['Ali', 'ne Uwimana']}, key)
        self.assertEqual(result['found_by_type'], {'date_of_birth': 1})


if __name__ == '__main__':
    unittest.main()
