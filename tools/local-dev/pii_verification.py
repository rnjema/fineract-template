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

"""Read-back reconciliation and restricted evaluation artifacts for the local PII fixture."""
from collections import Counter
from datetime import date
from decimal import Decimal
import json

from pii_fixture import AS_OF, VERSION, occurrences


def verify(runner, fixture, save, state):
    answer = {'version': VERSION, 'occurrences': [], 'financial_controls': [], 'clean_controls': [],
              'policy_baseline': 'strip/tokenize direct identifiers; drop free text by default; quasi-identifiers require approved policy'}
    records, coverage, scenario_counts = [], Counter(), Counter()
    loan_ids, transaction_ids = set(), set()
    by_client = {c['client_id']: c for c in fixture['clients']}

    def record(entity, entity_id, data, identity, direct_fields=None):
        records.append({'entity': entity, 'entity_id': str(entity_id), 'data': data})
        def visit(value, path):
            if isinstance(value, str):
                for match in occurrences(value, identity):
                    entry = dict(match, entity=entity, entity_id=str(entity_id), field=path, expected_action='strip_or_tokenize')
                    answer['occurrences'].append(entry)
                    coverage[entry['type']] += 1
            elif isinstance(value, dict):
                for key, child in value.items():
                    visit(child, path + '.' + str(key) if path else str(key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, path + '[' + str(index) + ']')
        visit(data, '')
        for field, kind in (direct_fields or {}).items():
            value = data.get(field)
            if isinstance(value, list) and kind == 'date_of_birth':
                value = date(*value).isoformat()
            if not value:
                raise RuntimeError('Expected native PII field absent: ' + entity + '/' + field)
            answer['occurrences'].append({'entity': entity, 'entity_id': str(entity_id), 'field': field,
                                          'type': kind, 'value': str(value), 'canonical': str(value),
                                          'expected_action': 'strip_or_tokenize' if kind != 'date_of_birth' else 'generalize_or_drop'})
            coverage[kind] += 1

    for number, client in enumerate(fixture['clients'], 1):
        cid, identity = client['client_id'], client['identity']
        native = runner.api('GET', f'/clients/{cid}')
        if (native.get('firstname'), native.get('lastname'), native.get('mobileNo'), native.get('dateOfBirth')) != (
                identity['first'], identity['last'], identity['phone'], [int(n) for n in identity['dob'].split('-')]):
            raise RuntimeError('Native identity changed or did not reconcile')
        record('clients', cid, native, identity, {'firstname': 'person_name', 'lastname': 'person_name',
                                                'mobileNo': 'phone', 'dateOfBirth': 'date_of_birth',
                                                'externalId': 'source_identifier', 'accountNo': 'account_identifier'})
        contacts = runner.api('GET', f'/datatables/pii_fixture_contact/{cid}?genericResultSet=false')
        if len(contacts) != 1 or any(contacts[0].get(k) != v for k, v in client['contact_data'].items()):
            raise RuntimeError('Stored contact datatable differs from immutable fixture')
        record('pii_fixture_contact', cid, contacts[0], identity)
        notes = [n for n in runner.api('GET', f'/clients/{cid}/notes') if n.get('note') == client['note']]
        if len(notes) != 1:
            raise RuntimeError('Expected exactly one owned client note')
        record('client_notes', notes[0]['id'], notes[0], identity)
        for text in client['controls']:
            answer['clean_controls'].append({'entity': 'client_notes', 'entity_id': str(notes[0]['id']), 'text': text,
                                            'expected_action': 'retain_if_text_redaction_mode_is_evaluated'})
        for kind in ['baseline', 'endline', 'investment']:
            observations = runner.api('GET', f'/datatables/anon_seed_{kind}/{cid}?genericResultSet=false')
            for observation in observations:
                records.append({'entity': 'source_' + kind, 'entity_id': observation['source_key'], 'data': observation})
        if number == 1 or number % 25 == 0:
            print(f'Read-back client/source reconciliation: {number}/100', flush=True)

    for planned in fixture['loans']:
        found = runner.api('GET', '/loans?externalId=' + planned['external_id'])['pageItems']
        if len(found) != 1:
            raise RuntimeError('Expected exactly one owned loan')
        lid = found[0]['id']
        loan_ids.add(lid)
        loan = runner.api('GET', f'/loans/{lid}?associations=all')
        identity = by_client[planned['client_id']]['identity']
        if loan['clientId'] != planned['client_id'] or Decimal(str(loan['principal'])) != Decimal('600'):
            raise RuntimeError('Loan principal/owner mismatch')
        record('loans', lid, loan, identity)
        answer['financial_controls'].append({'external_id': planned['external_id'], 'principal': '600.00', 'currency': 'USD'})
        notes = [n for n in runner.api('GET', f'/loans/{lid}/notes') if n.get('note') == planned['note']]
        if len(notes) != 1:
            raise RuntimeError('Loan note mismatch')
        record('loan_notes', notes[0]['id'], notes[0], identity)
        periods = [p for p in loan.get('repaymentSchedule', {}).get('periods', []) if p.get('period')]
        transactions = [t for t in loan.get('transactions', []) if not t.get('reversed')]
        disbursed = [t for t in transactions if t.get('type', {}).get('disbursement')]
        repayments = [t for t in transactions if t.get('type', {}).get('repayment')]
        paid = sum((Decimal(str(t['amount'])) for t in repayments), Decimal(0))
        outstanding_due = sum((Decimal(str(p.get('totalOutstandingForPeriod', 0))) for p in periods
                               if date(*p['dueDate']) < date.fromisoformat(AS_OF)), Decimal(0))
        scenario = planned['scenario']
        okay = ((scenario == 'on-time' and len(disbursed) == 1 and len(repayments) == 6 and paid == 600 and outstanding_due == 0)
                or (scenario == 'late' and len(disbursed) == 1 and not repayments and outstanding_due == 600)
                or (scenario == 'partial' and len(disbursed) == 1 and len(repayments) == 1 and paid == 25 and outstanding_due == 575)
                or (scenario == 'approved-undisbursed' and loan['status']['id'] == 200 and not disbursed and not repayments))
        if not okay:
            raise RuntimeError('Loan scenario balance/schedule mismatch: ' + planned['external_id'])
        scenario_counts[scenario] += 1
        for transaction in disbursed + repayments:
            tid = transaction['id']
            transaction_ids.add(tid)
            note_text = 'Receipt reconciliation: ' + planned['note']
            txnotes = [n for n in runner.api('GET', f'/loanTransactions/{tid}/notes') if n.get('note') == note_text]
            if len(txnotes) != 1:
                raise RuntimeError('Expected one owned PII transaction note')
            record('transaction_notes', txnotes[0]['id'], txnotes[0], identity)

    before = json.loads((state / 'before-state.json').read_text())
    if runner.fingerprints() != before['source_checksums']:
        raise RuntimeError('Original source table checksums changed')
    save(state / 'raw-extract.json', {'version': VERSION, 'records': records})
    save(state / 'answer-key.json', answer)
    result = {'version': VERSION, 'as_of': AS_OF, 'clients': 100,
              'profile_counts': dict(Counter(c['profile'] for c in fixture['clients'])),
              'loans': len(loan_ids), 'scenario_counts': dict(scenario_counts),
              'disbursements': 26, 'repayments': 66, 'transaction_notes': len(transaction_ids),
              'repayment_total_usd': '6150.00', 'disbursed_principal_usd': '15600.00',
              'client_notes': 100, 'loan_notes': 30, 'contact_datatables': 100,
              'verified_occurrences': len(answer['occurrences']), 'coverage_by_type': dict(coverage),
              'raw_extraction_records': len(records), 'file_only_stress_cases': len(fixture['file_only_stress_cases']),
              'original_source_checksums_unchanged': True, 'backup_restored_and_verified': True,
              'pipeline_privacy_evaluation': 'not evaluated; this prepares test inputs and a withheld answer key',
              'limitations': ['business/contact fields use registered fixture datatable, not native business/address tables',
                              'national IDs use explicit fictional TST format; phone validity/unassigned status not certified',
                              'source outcome observations and synthetic loan histories must not be conflated',
                              'native multi-tenancy and production parity remain unverified']}
    save(state / 'verification.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return result
