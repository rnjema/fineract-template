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

"""Apply the approved synthetic PII testbed only to the fixed local demo instance."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import urllib.parse

from pii_fixture import VERSION, AS_OF, generate_fixture, occurrences

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('anon_seed', HERE / 'Seed-AnonymizedWorkbench.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
STATE = HERE / '.runtime' / 'pii-testbed'
SOURCE_TABLES = ['capstone_anonymized_seed.raw_' + k for k in ['baseline', 'endline', 'investment']] + [
    'fineract_default.anon_seed_' + k for k in ['baseline', 'endline', 'investment']]
DATE_BODY = {'locale': 'en', 'dateFormat': 'yyyy-MM-dd'}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


class Runner(base.Seeder):
    def __init__(self):
        super().__init__(SimpleNamespace(username='mifos'), {}, [])
        self.state = STATE
        STATE.mkdir(parents=True, exist_ok=True)
        self.journal_path = STATE / 'journal.json'
        self.journal = json.loads(self.journal_path.read_text(encoding='utf-8')) if self.journal_path.exists() else {}
        self.stats = Counter()

    def command(self, key, method, path, body):
        payload_sha = base.digest(base.stable([method, path, body]).encode())
        prior = self.journal.get(key)
        if prior and prior['state'] == 'rejected':
            prior = None
        if prior:
            if prior['payload_sha'] != payload_sha:
                raise RuntimeError('Existing command payload changed: ' + key)
            if prior['state'] != 'complete':
                raise RuntimeError('Ambiguous interrupted command; reconcile privately before retry: ' + key)
            self.stats['commands_reused'] += 1
            return prior['result']
        self.journal[key] = {'payload_sha': payload_sha, 'state': 'pending', 'method': method, 'path': path}
        save(self.journal_path, self.journal)
        try:
            result = self.api(method, path, body)
        except RuntimeError:
            # Definite HTTP rejection is not an ambiguous successful mutation; keep evidence.
            import re
            if re.search(r'HTTP (400|401|403|404|405|422);', str(__import__('sys').exc_info()[1])):
                self.journal[key]['state'] = 'rejected'
                save(self.journal_path, self.journal)
            raise
        self.journal[key].update(state='complete', result=result)
        save(self.journal_path, self.journal)
        self.stats['commands_executed'] += 1
        return result

    def fingerprints(self):
        return self.sql('CHECKSUM TABLE ' + ','.join(SOURCE_TABLES) + ' EXTENDED;', True)

    def counts(self, container=None):
        names = ['fineract_default.m_client', 'fineract_default.m_loan'] + SOURCE_TABLES
        query = ' UNION ALL '.join(f'SELECT {base.literal(n)},COUNT(*) FROM {n}' for n in names) + ';'
        if container is None:
            return self.sql(query, True)
        return self.docker(['exec', '-i', container, 'mariadb', '-uroot', '--batch', '--skip-column-names'], query.encode()).decode().strip()

    def docker(self, args, input=None, timeout=240):
        result = subprocess.run([base.DOCKER] + args, input=input, capture_output=True, timeout=timeout)
        if result.returncode:
            (STATE / 'last-docker-error.log').write_bytes(result.stderr)
            raise RuntimeError('Local Docker operation failed; private error saved')
        return result.stdout

    def backup(self):
        evidence = STATE / 'backup-verified.json'
        if evidence.exists():
            info = json.loads(evidence.read_text())
            if base.digest((STATE / 'before-overlay.sql').read_bytes()) != info['sha256']:
                raise RuntimeError('Backup checksum changed')
            print('Previously restored backup checksum verified.', flush=True)
            return
        if self.journal:
            raise RuntimeError('Cannot create a before-overlay backup after mutations')
        modified = self.sql('SELECT COUNT(*) FROM capstone_anonymized_seed.cohort_manifest cm '
                            'JOIN fineract_default.m_client c ON c.id=cm.fineract_client_id '
                            'WHERE c.firstname<>"Anonymized";', True)
        if int(modified):
            raise RuntimeError('Fixture clients already changed; recover the original private state/backup instead of replacing it')
        before = {'counts': self.counts(), 'source_checksums': self.fingerprints()}
        save(STATE / 'before-state.json', before)
        dump = self.docker(['exec', base.CONTAINER, 'sh', '-c',
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump -uroot --single-transaction --hex-blob --databases fineract_tenants fineract_default capstone_anonymized_seed'], timeout=240)
        if len(dump) < 1000:
            raise RuntimeError('Backup unexpectedly small')
        (STATE / 'before-overlay.sql').write_bytes(dump)
        image = self.docker(['inspect', base.CONTAINER, '--format', '{{.Image}}']).decode().strip()
        temporary = 'capstone-pii-restore-check'
        self.docker(['run', '--rm', '-d', '--name', temporary, '--network', 'none', '--memory', '1792m',
                     '--tmpfs', '/var/lib/mysql:rw,size=1280m', '-e', 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1', image,
                     '--innodb-buffer-pool-size=64M', '--innodb-log-file-size=32M'])
        try:
            ready = False
            for _ in range(90):
                logs = self.docker(['logs', temporary]).decode(errors='replace')
                if 'MariaDB init process done. Ready for start up.' not in logs:
                    time.sleep(1)
                    continue
                result = subprocess.run([base.DOCKER, 'exec', temporary, 'mariadb-admin', '-uroot', 'ping'], capture_output=True)
                if result.returncode == 0:
                    ready = True
                    break
                time.sleep(1)
            if not ready:
                raise RuntimeError('Temporary restore database did not become ready')
            self.docker(['exec', '-i', temporary, 'mariadb', '-uroot'], dump)
            restored = self.counts(temporary)
            if restored != before['counts']:
                raise RuntimeError('Restored backup counts differ from workbench')
            save(evidence, {'sha256': base.digest(dump), 'bytes': len(dump), 'restore_counts_match': True,
                            'temporary_database_network': 'none', 'original_source_checksums': before['source_checksums']})
            print('Backup restored in isolated temporary MariaDB; source/client/loan counts match.', flush=True)
        except Exception:
            (STATE / 'restore-container.log').write_bytes(self.docker(['logs', temporary]))
            raise
        finally:
            self.docker(['stop', temporary])

    def fixture(self):
        path = STATE / 'fixture.json'
        if path.exists():
            fixture = json.loads(path.read_text(encoding='utf-8'))
            if fixture['version'] != VERSION:
                raise RuntimeError('Unknown fixture version')
            expected = (STATE / 'fixture.sha256').read_text().strip()
            if base.digest(base.stable(fixture).encode()) != expected:
                raise RuntimeError('Saved immutable fixture was modified')
            return fixture
        rows = self.sql('SELECT fineract_client_id,external_id,source_country FROM capstone_anonymized_seed.cohort_manifest '
                        'WHERE import_state="complete" ORDER BY external_id;', True)
        clients = [{'id': int(r[0]), 'external_id': r[1], 'country': r[2]} for r in (line.split('\t') for line in rows.splitlines())]
        fixture = generate_fixture(clients)
        save(path, fixture)
        (STATE / 'fixture.sha256').write_text(base.digest(base.stable(fixture).encode()) + '\n')
        return fixture

    def ensure_contact_table(self):
        name = 'pii_fixture_contact'
        known = {r['registeredTableName'] for r in self.api('GET', '/datatables?apptable=m_client')}
        if name not in known:
            fields = {'fixture_version': 50, 'business_label': 250, 'location_hint': 500, 'email': 200,
                      'national_id': 80, 'alternate_contact': 250, 'free_text': 1000}
            self.command('contact-table', 'POST', '/datatables', {'datatableName': name, 'apptableName': 'm_client',
                'entitySubType': 'PERSON', 'multiRow': False,
                'columns': [{'name': n, 'type': 'String', 'length': length, 'mandatory': True} for n, length in fields.items()]})

    def note(self, kind, entity_id, text, key):
        path = f'/{kind}/{entity_id}/notes'
        existing = [n for n in self.api('GET', path) if n.get('note') == text]
        if len(existing) > 1:
            raise RuntimeError('Duplicate owned note')
        if not existing:
            self.command(key, 'POST', path, {'note': text})
        stored = [n for n in self.api('GET', path) if n.get('note') == text]
        if len(stored) != 1:
            raise RuntimeError('Note did not reconcile')
        return stored[0]

    def overlay(self, client):
        cid = client['client_id']
        current = self.api('GET', f'/clients/{cid}')
        if current['externalId'] != client['external_id'] or current['officeId'] != 1:
            raise RuntimeError('Client ownership mismatch')
        before_path = STATE / 'before-clients' / (str(cid) + '.json')
        if not before_path.exists():
            if current.get('firstname') != 'Anonymized':
                raise RuntimeError('Client no longer has expected initial demo label')
            save(before_path, {'client': current, 'provenance': self.api('GET', f'/datatables/anon_seed_provenance/{cid}')})
        identity = client['identity']
        body = dict(DATE_BODY, firstname=identity['first'], lastname=identity['last'], dateOfBirth=identity['dob'],
                    mobileNo=identity['phone'], externalId=client['external_id'], submittedOnDate='2026-04-01')
        key = f'client-{cid}-identity'
        self.command(key, 'PUT', f'/clients/{cid}', body)
        current = self.api('GET', f'/clients/{cid}')
        if current['firstname'] != identity['first'] or current['lastname'] != identity['last'] or current.get('mobileNo') != identity['phone']:
            raise RuntimeError('Stored identity differs from intended fixture')
        contact_path = f'/datatables/pii_fixture_contact/{cid}'
        data = self.api('GET', contact_path + '?genericResultSet=false')
        if not data:
            self.command(f'client-{cid}-contact', 'POST', contact_path, client['contact_data'])
        else:
            if len(data) != 1 or any(data[0].get(k) != v for k, v in client['contact_data'].items()):
                raise RuntimeError('Existing fixture contacts changed; refuse silent overwrite')
        self.note('clients', cid, client['note'], f'client-{cid}-note')
        provenance = {'seed_version': 'anonymized-export-demo-v1', 'source_country': client['country'],
                      'fixture_fields': json.dumps({'overlay': VERSION, 'identity': 'All names, DOB, phone and fixture contacts are generated',
                         'submittedOnDate': '2026-04-01 generated lifecycle date, not source history',
                         'activation': 'Generated only for loan fixtures', 'source_observations': 'unchanged; not synthetic loan history',
                         'answer_key': 'restricted local runtime'}, separators=(',', ':'))}
        self.command(f'client-{cid}-provenance', 'PUT', f'/datatables/anon_seed_provenance/{cid}', provenance)

    def product(self):
        name = 'SYNTHETIC PII Workbench USD v1'
        found = [p for p in self.api('GET', '/loanproducts') if p['name'] == name]
        if len(found) > 1:
            raise RuntimeError('Duplicate fixture product')
        if found:
            return found[0]['id']
        body = dict(DATE_BODY, name=name, shortName='PII1', description='Synthetic testbed only; not source loan terms',
                    currencyCode='USD', digitsAfterDecimal=2, inMultiplesOf=0, principal='600.00',
                    minPrincipal='100.00', maxPrincipal='10000.00', numberOfRepayments=6, repaymentEvery=1,
                    repaymentFrequencyType=2, interestRatePerPeriod='0', interestRateFrequencyType=2,
                    amortizationType=1, interestType=1, interestCalculationPeriodType=1,
                    transactionProcessingStrategyId=1, accountingRule=1, isInterestRecalculationEnabled=False,
                    daysInYearType=1, daysInMonthType=1, overdueDaysForNPA=30, allowableDSCR='1.20')
        result = self.command('loan-product', 'POST', '/loanproducts', body)
        return result['resourceId']

    def ensure_local_loan_schema(self):
        column = self.sql('SELECT COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA="fineract_default" '
                          'AND TABLE_NAME="m_loan" AND COLUMN_NAME="office_id";', True)
        if not column:
            if int(self.sql('SELECT COUNT(*) FROM fineract_default.m_loan;', True)) != 0:
                raise RuntimeError('Missing local office column on populated loan table requires separate review')
            self.sql('ALTER TABLE fineract_default.m_loan ADD COLUMN office_id BIGINT NULL, '
                     'ADD CONSTRAINT FK_capstone_loan_office FOREIGN KEY (office_id) REFERENCES fineract_default.m_office(id);')
            save(STATE / 'loan-schema-compatibility.json', {
                'scope': 'local-only empty loan table compatibility correction', 'column': 'm_loan.office_id BIGINT NULL',
                'reason': 'Running entity maps office_id; original migrated table omitted it',
                'foreign_key': 'FK_capstone_loan_office -> m_office.id', 'core_ledger_rows_directly_written': 0,
                'liquibase_history_modified': False, 'original_jar_modified': False})

    def loan(self, loan, product_id):
        cid, external = loan['client_id'], loan['external_id']
        payment_types = [p for p in self.api('GET', '/paymenttypes') if p.get('isCashPayment') and not p.get('isMobileMoney')]
        if len(payment_types) != 1:
            raise RuntimeError('Explicit local cash-like payment type is not unique')
        payment_type_id = payment_types[0]['id']
        client = self.api('GET', f'/clients/{cid}')
        if not client['active']:
            self.command(f'client-{cid}-activate', 'POST', f'/clients/{cid}?command=activate',
                         dict(DATE_BODY, activationDate='2026-04-01'))
        found = self.api('GET', '/loans?' + urllib.parse.urlencode({'externalId': external}))['pageItems']
        if len(found) > 1:
            raise RuntimeError('Duplicate fixture loan external ID')
        if found:
            lid = found[0]['id']
            if found[0]['clientId'] != cid or found[0]['loanProductId'] != product_id:
                raise RuntimeError('Existing loan ownership mismatch')
        else:
            funds = [f for f in self.api('GET', '/funds') if f['name'] == 'SYNTHETIC PII Fixture Fund']
            if not funds:
                self.command('fixture-fund', 'POST', '/funds', {'name': 'SYNTHETIC PII Fixture Fund', 'externalId': VERSION + '-fund'})
                funds = [f for f in self.api('GET', '/funds') if f['name'] == 'SYNTHETIC PII Fixture Fund']
            codes = {c['name']: c['id'] for c in self.api('GET', '/codes')}
            purpose_path = '/codes/' + str(codes['LoanPurpose']) + '/codevalues'
            purposes = [v for v in self.api('GET', purpose_path) if v['name'] == 'Synthetic working capital']
            if not purposes:
                self.command('fixture-purpose', 'POST', purpose_path,
                             {'name': 'Synthetic working capital', 'position': 90, 'isActive': True})
                purposes = [v for v in self.api('GET', purpose_path) if v['name'] == 'Synthetic working capital']
            departments = [v for v in self.api('GET', '/codes/' + str(codes['Department']) + '/codevalues') if v['name'] == 'Micro-Enterprise']
            if len(funds) != 1 or len(purposes) != 1 or len(departments) != 1:
                raise RuntimeError('Loan fixture catalogs not uniquely identified')
            body = dict(DATE_BODY, clientId=cid, productId=product_id, externalId=external,
                        principal=loan['principal'], loanTermFrequency=6, loanTermFrequencyType=2,
                        numberOfRepayments=6, repaymentEvery=1, repaymentFrequencyType=2,
                        interestRatePerPeriod='0', amortizationType=1, interestType=1,
                        interestCalculationPeriodType=1, transactionProcessingStrategyId=1,
                        expectedDisbursementDate='2026-04-03', submittedOnDate='2026-04-02', loanType='individual',
                        applicationDate='2026-04-02', accountNo='PII1' + external.rsplit('-', 1)[-1],
                        description=loan['note'], fundId=funds[0]['id'], department=departments[0]['id'], loanPurposeId=purposes[0]['id'])
            result = self.command(external + '-apply', 'POST', '/loans', body)
            lid = result.get('loanId') or result['resourceId']
        self.note('loans', lid, loan['note'], external + '-note')
        detail = self.api('GET', f'/loans/{lid}?associations=all')
        if detail['status']['id'] == 100:
            self.command(external + '-approve', 'POST', f'/loans/{lid}?command=approve',
                         dict(DATE_BODY, approvedOnDate='2026-04-02', paymentTypeId=payment_type_id))
        if loan['scenario'] != 'approved-undisbursed':
            detail = self.api('GET', f'/loans/{lid}?associations=all')
            if detail['status']['id'] == 200:
                self.command(external + '-disburse', 'POST', f'/loans/{lid}?command=disburse',
                             dict(DATE_BODY, actualDisbursementDate='2026-04-03', paymentTypeId=payment_type_id))
            detail = self.api('GET', f'/loans/{lid}?associations=all')
            periods = [p for p in detail['repaymentSchedule']['periods'] if p.get('period')]
            if loan['scenario'] in ['on-time', 'partial']:
                for p in periods if loan['scenario'] == 'on-time' else periods[:1]:
                    amount = Decimal(str(p['totalDueForPeriod'])) if loan['scenario'] == 'on-time' else Decimal('25.00')
                    # Intended dates/amounts are immutable; successful journal results prevent financial retries.
                    due = date(*p['dueDate']).isoformat()
                    self.command(external + '-repay-' + str(p['period']), 'POST', f'/loans/{lid}/transactions?command=repayment',
                                 dict(DATE_BODY, transactionDate=due, transactionAmount=str(amount),
                                      externalId=external + '-p' + str(p['period']), paymentTypeId=payment_type_id))
            detail = self.api('GET', f'/loans/{lid}?associations=all')
            for transaction in detail.get('transactions', []):
                if not transaction.get('reversed') and (transaction.get('type', {}).get('disbursement') or transaction.get('type', {}).get('repayment')):
                    txid = transaction['id']
                    self.note('loanTransactions', txid, 'Receipt reconciliation: ' + loan['note'], external + f'-transaction-{txid}-note')
        return lid

    def apply(self, limit=None):
        self.backup()
        fixture = self.fixture()
        for hook in self.api('GET', '/hooks'):
            if hook.get('isActive'):
                hook_id = hook['id']
                before_hook = STATE / f'before-hook-{hook_id}.json'
                if not before_hook.exists():
                    save(before_hook, self.api('GET', f'/hooks/{hook_id}'))
                self.command(f'disable-hook-{hook_id}', 'PUT', f'/hooks/{hook_id}', {'isActive': False})
        if any(h.get('isActive') for h in self.api('GET', '/hooks')):
            raise RuntimeError('Hooks must be disabled in the local PII testbed')
        self.ensure_contact_table()
        self.ensure_local_loan_schema()
        clients = fixture['clients'][:limit] if limit else fixture['clients']
        for i, client in enumerate(clients, 1):
            self.overlay(client)
            if i == 1 or i % 20 == 0:
                print(f'Identity/contact/note overlays reconciled: {i}/{len(clients)}', flush=True)
        product = self.product()
        eligible = {c['client_id'] for c in clients}
        loans = [loan for loan in fixture['loans'] if loan['client_id'] in eligible]
        if limit:
            loans = loans[:1]
        for i, loan in enumerate(loans, 1):
            self.loan(loan, product)
            print(f'Loan lifecycle reconciled: {i}/{len(loans)}', flush=True)
        if self.fingerprints() != json.loads((STATE / 'before-state.json').read_text())['source_checksums']:
            raise RuntimeError('Original staging/observation fingerprints changed')
        print('Original source tables unchanged. Commands: ' + json.dumps(dict(self.stats)), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['backup', 'generate', 'apply', 'verify'])
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    runner = Runner()
    if args.phase == 'backup':
        runner.backup()
    elif args.phase == 'generate':
        fixture = runner.fixture()
        print(json.dumps({'clients': len(fixture['clients']), 'loans': len(fixture['loans']), 'version': VERSION}))
    elif args.phase == 'verify':
        from pii_verification import verify
        verify(runner, runner.fixture(), save, STATE)
    else:
        runner.apply(1 if args.pilot else None)


if __name__ == '__main__':
    main()
