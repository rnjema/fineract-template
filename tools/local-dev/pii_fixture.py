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

"""Deterministic synthetic identities; no original person identities are reconstructed."""
from collections import defaultdict
from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).parent / '.runtime' / 'pii-deps'))
from faker import Faker
from faker.providers import BaseProvider

VERSION = 'pii-workbench-v1'
FAKER_VERSION = '40.43.0'
AS_OF = '2026-10-20'
# Independently combined examples, not a model of ethnicity or population frequency.
POOLS = {
    'Rwanda': (['Aline', 'Jean Claude', 'Diane', 'Emmanuel', 'Chantal', 'Eric', 'Clarisse', 'Aimée'],
               ['Uwimana', 'Niyonzima', 'Mukamana', 'Habimana', 'Iradukunda', 'Nsengimana', 'Uwera', 'Mugisha']),
    'Ethiopia': (['Hana', 'Dawit', 'Selam', 'Abel', 'Tigist', 'Mekdes', 'Yohannes', 'Tsion'],
                 ['Tesfaye', 'Bekele', 'Abebe', 'Kebede', 'Getachew', 'Alemu', 'Tadesse', 'Worku']),
    'South Sudan': (['Nyandeng', 'Deng', 'Ajak', 'Mary', 'John', 'Adut', 'Peter', 'Nyabol'],
                    ['Dut', 'Chol', 'Akol', 'Lual', 'Bol', 'Garang', 'Mabior', 'Wani']),
    'Kenya': (['Amina', 'Wanjiku', 'Kamau', 'Njeri', 'Otieno', 'Achieng', 'Fatuma', 'Baraka'],
              ['Mwangi', 'Odhiambo', 'Njoroge', 'Hassan', 'Wambui', 'Omondi', 'Kiptoo', 'Muthoni'])
}
PREFIX = {'Rwanda': '250', 'Ethiopia': '251', 'South Sudan': '211', 'Kenya': '254'}
TOWNS = {'Rwanda': ['Kigali', 'Huye', 'Musanze'], 'Ethiopia': ['Addis Ababa', 'Hawassa', 'Bahir Dar'],
         'South Sudan': ['Juba', 'Wau', 'Bor'], 'Kenya': ['Nairobi', 'Kisumu', 'Mombasa']}


class RegionalProvider(BaseProvider):
    def regional_name(self, country):
        given, family = POOLS[country]
        return self.random_element(given), self.random_element(family)


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def occurrences(text, identity):
    result = []
    for kind, keys in {'person_name': ['full_name', 'contact_name'], 'phone': ['phone', 'phone_spaced'],
                       'email': ['email'], 'national_id': ['national_id'], 'date_of_birth': ['dob']}.items():
        for key in keys:
            value = identity.get(key, '')
            if not value:
                continue
            for match in re.finditer(re.escape(value), text, flags=re.IGNORECASE):
                result.append({'type': kind, 'start': match.start(), 'end': match.end(),
                               'value': match.group(), 'canonical': identity.get('phone') if kind == 'phone' else value})
    return sorted(result, key=lambda x: (x['start'], x['end'], x['type']))


def generate_fixture(clients):
    if importlib.metadata.version('Faker') != FAKER_VERSION:
        raise RuntimeError('Install the exact pinned Faker version before generating a new fixture')
    grouped = defaultdict(list)
    for client in clients:
        grouped[client['country']].append(client)
    if {c: len(v) for c, v in grouped.items()} != {c: 25 for c in POOLS}:
        raise ValueError('Expected the approved 25-client cohort from each of four countries')
    output = []
    for country in POOLS:
        for ordinal, client in enumerate(sorted(grouped[country], key=lambda c: c['external_id']), 1):
            seed = int(hashlib.sha256((VERSION + client['external_id']).encode()).hexdigest()[:16], 16)
            rng = random.Random(seed)
            profile = 'regional' if ordinal <= 20 else 'global'
            locale = 'en_GB' if profile == 'regional' else ['fr_FR', 'en_GB', 'de_DE', 'es_ES', 'en_US'][ordinal - 21]
            fake = Faker(locale)
            fake.seed_instance(seed)
            fake.add_provider(RegionalProvider)
            first, last = fake.regional_name(country) if profile == 'regional' else (fake.first_name(), fake.last_name())
            # Deliberately include supported punctuation/Unicode, separate from ethnic profiles.
            if country == 'Rwanda' and ordinal == 1:
                first = 'Aimée'
            if country == 'Kenya' and ordinal == 2:
                last = "O'Nyango"
            tag = hashlib.sha256(client['external_id'].encode()).hexdigest()[:10]
            phone = '+' + PREFIX[country] + '7' + str(seed % 100000000).zfill(8)
            phone_spaced = phone[:4] + ' ' + phone[4:7] + '-' + phone[7:]
            dob = date(rng.randint(1965, 2001), rng.randint(1, 12), rng.randint(1, 28)).isoformat()
            identity = {'first': first, 'last': last, 'full_name': first + ' ' + last,
                        'email': 'contact.' + tag + '@example.org', 'phone': phone, 'phone_spaced': phone_spaced,
                        'dob': dob, 'national_id': 'TST-' + PREFIX[country] + '-' + str(seed % 1000000000).zfill(9),
                        'contact_name': fake.first_name() + ' ' + fake.last_name()}
            address = f"Plot {rng.randint(11, 890)}, Market Lane, {rng.choice(TOWNS[country])}; ask {identity['full_name']} on {phone_spaced}"
            note = (f"Client {identity['full_name']} requested a market visit. Contact {phone_spaced}; "
                    f"email {identity['email']}. Identity copy reference {identity['national_id']}. "
                    f"Next of kin: {identity['contact_name']}. DOB recorded {dob}.\n"
                    f"Copied phone in delivery instructions: {phone}; alias: {identity['full_name'].upper()}. "
                    "Clean control: stock count 125; invoice total USD 600; market opens at 08:30.")
            output.append({'client_id': client['id'], 'external_id': client['external_id'], 'country': country,
                           'profile': profile, 'locale': locale, 'identity': identity, 'note': note,
                           'contact_data': {'fixture_version': VERSION, 'business_label': identity['full_name'] + ' Market Supplies',
                                            'location_hint': address, 'email': identity['email'],
                                            'national_id': identity['national_id'], 'alternate_contact': identity['contact_name'] + ' / ' + phone,
                                            'free_text': json.dumps({'delivery_contact': identity['full_name'], 'callback': phone_spaced,
                                                                     'email': identity['email']}, ensure_ascii=False)},
                           'controls': ['stock count 125', 'invoice total USD 600', 'market opens at 08:30']})
    # Round-robin countries gives every country loan coverage.
    loan_clients = [output[country_index * 25 + ordinal] for ordinal in range(8) for country_index in range(4)][:30]
    scenarios = ['on-time'] * 10 + ['late'] * 10 + ['partial'] * 6 + ['approved-undisbursed'] * 4
    loans = [{'external_id': VERSION + '-loan-' + str(i + 1).zfill(3), 'client_id': c['client_id'],
              'scenario': scenario, 'principal': '600.00', 'note':
              f"Business visit for {c['identity']['full_name']}; callback {c['identity']['phone_spaced']}; "
              f"document {c['identity']['national_id']}; email {c['identity']['email']}."}
             for i, (c, scenario) in enumerate(zip(loan_clients, scenarios))]
    stress = [
        {'case': 'long_note', 'raw': output[0]['note'] * 80},
        {'case': 'invisible_unicode', 'raw': output[0]['identity']['email'].replace('@', '\u200b@')},
        {'case': 'escaped_nested_text', 'raw': json.dumps({'notes': output[1]['note']})},
        {'case': 'invalid_typed_values', 'raw': {'dateOfBirth': '2039-02-31', 'age': '-7', 'principal': '999999999999999999999.99'}},
        {'case': 'single_name', 'raw': {'full_name': 'Nyandeng', 'note': 'Single-name form must survive ingestion without invented surname'}}
    ]
    return {'version': VERSION, 'faker_version': FAKER_VERSION, 'as_of': AS_OF, 'clients': output,
            'loans': loans, 'file_only_stress_cases': [dict(x, storage='file-only') for x in stress]}
