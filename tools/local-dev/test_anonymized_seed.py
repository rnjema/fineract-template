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
import unittest

spec=importlib.util.spec_from_file_location('seed',Path(__file__).with_name('Seed-AnonymizedWorkbench.py'))
seed=importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

class SeedTests(unittest.TestCase):
    def test_duplicate_header_alias_is_distinct_from_first(self):
        self.assertNotEqual(seed.column_name('gender'),seed.column_name('gender__2'))
        self.assertEqual(seed.column_name('BaselineEndlineClientId'),'src_baseline_endline_client_id')

    def test_sql_values_are_encoded_not_interpolated(self):
        value="O'Neil; DROP TABLE x; -- \u00e9"
        expression=seed.literal(value)
        self.assertNotIn('DROP',expression)
        encoded=expression.split('0x')[1].split(' ')[0]
        self.assertEqual(bytes.fromhex(encoded).decode(),value)

    def test_country_namespaces_and_ambiguous_survey_links(self):
        investments=[]; surveys=[]
        for country in seed.COUNTRIES:
            for i in range(25):
                investments.append({'country':country,'ClientId':str(i),'BaselineEndlineClientId':'s'+str(i)})
                surveys.append({'country':country,'client_id':'s'+str(i)})
        investments[1]['BaselineEndlineClientId']='s0'
        data={'investment':{'rows':investments},'baseline':{'rows':surveys},'endline':{'rows':surveys}}
        cohort=seed.choose_cohort(data)
        self.assertEqual(len(cohort),100)
        self.assertEqual(len({c['external_id'] for c in cohort}),100)
        self.assertTrue(all(c['survey_key'] is None for c in cohort if c['key'][0]=='Rwanda' and c['key'][1] in ['0','1']))
        reversed_data={**data,'investment':{'rows':list(reversed(investments))}}
        self.assertEqual([c['external_id'] for c in cohort], [c['external_id'] for c in seed.choose_cohort(reversed_data)])

if __name__=='__main__':
    unittest.main()
