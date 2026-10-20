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

"""Seed full source staging and an approved 100-client API cohort in the named LOCAL workbench.

Source financial snapshots are observations, not reconstructed banking transactions.
No production connections, guessed repayments, native tenant registrations or record deletion.
"""
import argparse
import base64
from collections import Counter, defaultdict
from datetime import date
import hashlib
import io
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(r'D:\Projects\schoolwork\eai_capstone_project\inkomoko-earlywarning-system\ml\Anomynized data\Anomynized data\Anomynized data')
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
SCHEMA = 'capstone_anonymized_seed'
CONTAINER = 'capstone-fineract-local-db-1'
BASE = 'http://127.0.0.1:9002/fineract-provider/api/v1'
COUNTRIES = {'Rwanda':'RW','Ethiopia':'ET','South Sudan':'SS','Kenya':'KE'}

def digest(value):
    return hashlib.sha256(value).hexdigest()

def stable(value):
    return json.dumps(value, ensure_ascii=False, separators=(',',':'))

def literal(value):
    if value is None:
        return 'NULL'
    return "CONVERT(0x" + str(value).encode('utf-8').hex() + " USING utf8mb4)" if str(value) else "''"

def column_name(header):
    name = re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',header)
    name = 'src_' + re.sub('[^a-z0-9]+','_',name.lower()).strip('_')
    if len(name)>60:
        raise RuntimeError('Source column name exceeds supported demo mapping')
    return name

def load_sources(source):
    data = {}
    for kind, pattern in [('baseline','baseline_*.csv'),('endline','endline_*.csv'),('investment','Investment*.csv')]:
        files = list(source.glob(pattern))
        if len(files)!=1:
            raise RuntimeError('Expected exactly one reviewed '+kind+' source CSV')
        path = files[0]
        raw = path.read_bytes()
        try:
            text=raw.decode('utf-8-sig'); encoding='utf-8-sig'
        except UnicodeDecodeError:
            text=raw.decode('cp1252'); encoding='cp1252'
        reader=csv.reader(io.StringIO(text,newline=''))
        original=next(reader)
        counts=Counter(); headers=[]
        for value in original:
            counts[value]+=1
            headers.append(value if counts[value]==1 else value+'__'+str(counts[value]))
        columns=[column_name(h) for h in headers]
        if len(set(columns))!=len(columns):
            raise RuntimeError('Source headers collide after normalization')
        rows=[]
        for number, values in enumerate(reader,2):
            if len(values)!=len(headers):
                raise RuntimeError('Unexpected row width in '+kind)
            row=dict(zip(headers,values))
            row['_source_row']=number
            row['_values']=values
            rows.append(row)
        data[kind]={'path':path,'sha':digest(raw),'encoding':encoding,'original_headers':original,
            'headers':headers,'columns':columns,'rows':rows}
    return data

def choose_cohort(data):
    investments=defaultdict(list)
    references=defaultdict(set)
    reverse=defaultdict(set)
    surveys={(r['country'].strip(),r['client_id'].strip()) for kind in ['baseline','endline'] for r in data[kind]['rows']}
    for row in data['investment']['rows']:
        key=(row['country'].strip(),row['ClientId'].strip())
        if key[0] not in COUNTRIES or not key[1]:
            raise RuntimeError('Unknown country or missing investment client identity')
        investments[key].append(row)
        if row['BaselineEndlineClientId'].strip():
            ref=(key[0],row['BaselineEndlineClientId'].strip())
            references[key].add(ref)
            reverse[ref].add(key)
    safe={k:next(iter(refs)) for k,refs in references.items() if len(refs)==1 and
        next(iter(refs)) in surveys and len(reverse[next(iter(refs))])==1}
    selected=[]
    for country, code in COUNTRIES.items():
        keys=[k for k in investments if k[0]==country]
        keys.sort(key=lambda k:(k not in safe,digest(stable(k).encode())))
        if len(keys)<25:
            raise RuntimeError('Insufficient country coverage for the approved cohort')
        for index,key in enumerate(keys[:25],1):
            selected.append({'key':key,'code':code,'ordinal':index,'survey_key':safe.get(key),
                'external_id':'ANONSEED-v1-'+digest(stable(key).encode())[:32],
                'investments':investments[key]})
    return selected

class Seeder:
    def __init__(self,args,data,cohort):
        self.args=args; self.data=data; self.cohort=cohort
        self.state=HERE/'.runtime/anonymized-seed'
        self.state.mkdir(parents=True,exist_ok=True)
        credentials=(args.username+':'+os.environ.get('LOCAL_DEMO_PASSWORD','password')).encode()
        self.headers={'Authorization':'Basic '+base64.b64encode(credentials).decode(),
            'Fineract-Platform-TenantId':'default','Content-Type':'application/json'}
        self.summary={'source_rows':{},'api_clients_created':0,'api_clients_reused':0,
            'api_snapshot_rows_created':{},'api_snapshot_rows_reused':{},'live_ledger_loans_created':0,
            'repayment_transactions_created':0,'native_tenants_created':0}

    def sql(self,statement,query=False):
        argv=[DOCKER,'exec','-i',CONTAINER,'sh','-c',
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --default-character-set=utf8mb4 --batch --skip-column-names -uroot']
        result=subprocess.run(argv,input=statement.encode(),capture_output=True,timeout=120)
        if result.returncode:
            (self.state/'last-database-error.log').write_bytes(result.stderr)
            raise RuntimeError('Local database operation failed; private error log saved')
        return result.stdout.decode().strip() if query else None

    def api(self,method,path,body=None,allow_missing=False):
        if not path.startswith('/') or path.startswith('//'):
            raise RuntimeError('Invalid fixed local API path')
        request=urllib.request.Request(BASE+path,data=stable(body).encode() if body is not None else None,
            headers=self.headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=40) as response:
                raw=response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw=error.read()
            if allow_missing and error.code==404:
                return None
            (self.state/'last-api-error.json').write_bytes(raw)
            raise RuntimeError(f'Local API {method} failed with HTTP {error.code}; private error saved') from None

    def stage(self):
        self.sql(f'CREATE DATABASE IF NOT EXISTS {SCHEMA} CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;'
            f'CREATE TABLE IF NOT EXISTS {SCHEMA}.seed_files(file_sha CHAR(64) PRIMARY KEY,filename VARCHAR(255) UNIQUE NOT NULL,'
            'encoding VARCHAR(20) NOT NULL,expected_rows INT NOT NULL,header_json LONGTEXT NOT NULL,column_json LONGTEXT NOT NULL);'
            f'CREATE TABLE IF NOT EXISTS {SCHEMA}.cohort_manifest(external_id VARCHAR(64) PRIMARY KEY,'
            'source_country VARCHAR(100) NOT NULL,source_client_id TEXT NOT NULL,survey_client_id TEXT NULL,'
            'fineract_client_id BIGINT NULL,payload_sha CHAR(64) NOT NULL,import_state VARCHAR(30) NOT NULL);')
        for kind,table in self.data.items():
            existing=self.sql(f'SELECT file_sha FROM {SCHEMA}.seed_files WHERE filename={literal(table["path"].name)};',True)
            if existing and existing!=table['sha']:
                raise RuntimeError('Source file changed after a previous load; use a reviewed new import version')
            definitions=','.join('`'+c+'` TEXT NULL' for c in table['columns'])
            self.sql(f'CREATE TABLE IF NOT EXISTS {SCHEMA}.raw_{kind}(_source_sha CHAR(64) NOT NULL,'
                '_source_row INT NOT NULL,_row_sha CHAR(64) NOT NULL,_payload_json LONGTEXT NOT NULL,'+definitions+
                ',PRIMARY KEY(_source_sha,_source_row)) ENGINE=InnoDB;')
            self.sql(f'INSERT INTO {SCHEMA}.seed_files VALUES('+','.join(map(literal,[table['sha'],table['path'].name,
                table['encoding'],len(table['rows']),stable(table['original_headers']),stable(table['columns'])]))+
                ') ON DUPLICATE KEY UPDATE file_sha=VALUES(file_sha);')
            previous=self.sql(f'SELECT COUNT(*),COALESCE(SUM(SHA2(_payload_json,256)<>_row_sha),0) '
                f'FROM {SCHEMA}.raw_{kind} WHERE _source_sha={literal(table["sha"])};',True).split('\t')
            if list(map(int,previous))==[len(table['rows']),0]:
                self.verify_raw_fields(kind,table)
                self.summary['source_rows'][kind]=len(table['rows'])
                print(f'Existing source staging reconciled; reused {kind}: {len(table["rows"])} rows',flush=True)
                continue
            names=['_source_sha','_source_row','_row_sha','_payload_json']+table['columns']
            for offset in range(0,len(table['rows']),200):
                values=[]
                for row in table['rows'][offset:offset+200]:
                    payload=stable(row['_values'])
                    values.append('('+','.join(map(literal,[table['sha'],row['_source_row'],digest(payload.encode()),payload]+row['_values']))+')')
                self.sql('START TRANSACTION; INSERT INTO '+SCHEMA+'.raw_'+kind+'('+','.join('`'+n+'`' for n in names)+') VALUES '+
                    ','.join(values)+' ON DUPLICATE KEY UPDATE _source_row=VALUES(_source_row); COMMIT;')
            count=self.sql(f'SELECT COUNT(*),SUM(SHA2(_payload_json,256)<>_row_sha) FROM {SCHEMA}.raw_{kind} '
                f'WHERE _source_sha={literal(table["sha"])};',True).split('\t')
            if list(map(int,count))!=[len(table['rows']),0]:
                raise RuntimeError('Raw source row/hash reconciliation failed')
            self.verify_raw_fields(kind,table)
            self.summary['source_rows'][kind]=len(table['rows'])
            print(f'Staged and hash-reconciled {kind}: {len(table["rows"])} rows',flush=True)

    def verify_raw_fields(self,kind,table):
        differences=' OR '.join(f'NOT (BINARY `{col}` <=> BINARY JSON_UNQUOTE(JSON_EXTRACT(_payload_json,"$[{i}]")))'
            for i,col in enumerate(table['columns']))
        bad=self.sql(f'SELECT COUNT(*) FROM {SCHEMA}.raw_{kind} WHERE _source_sha={literal(table["sha"])} '
            f'AND ({differences});',True)
        if int(bad):
            raise RuntimeError('Structured staging columns differ from original source values')

    def ensure_datatables(self):
        registry=self.api('GET','/datatables?apptable=m_client')
        known={r['registeredTableName'] for r in registry}
        for kind,table in self.data.items():
            name='anon_seed_'+kind
            columns=[{'name':'source_key','type':'String','length':96,'mandatory':True},
                {'name':'source_sha256','type':'String','length':64,'mandatory':True},
                {'name':'source_row','type':'Number','mandatory':True}]
            for index,col in enumerate(table['columns']):
                length=max(16,max(len(row['_values'][index].strip()) for row in table['rows'])+8)
                if length>1000:
                    raise RuntimeError('Source field needs an explicitly reviewed long-text API mapping')
                columns.append({'name':col,'type':'String','length':length,'mandatory':False})
            if name not in known:
                self.api('POST','/datatables',{'datatableName':name,'apptableName':'m_client','entitySubType':'PERSON',
                    'multiRow':True,'columns':columns})
            info=self.api('GET','/datatables/'+name)
            actual={h['columnName'] for h in info['columnHeaderData']}
            if not {c['name'] for c in columns}.issubset(actual):
                raise RuntimeError('Existing API datatable does not match the reviewed source columns')
            # This fork rejects a column-level "unique" API option. Enforce source-row
            # uniqueness only on these newly owned extension tables, never core ledger tables.
            self.sql(f'CREATE UNIQUE INDEX IF NOT EXISTS {name}_source_key ON fineract_default.{name}(source_key);')
            self.summary['api_snapshot_rows_created'][kind]=0
            self.summary['api_snapshot_rows_reused'][kind]=0
        provenance='anon_seed_provenance'
        if provenance not in known:
            self.api('POST','/datatables',{'datatableName':provenance,'apptableName':'m_client',
                'entitySubType':'PERSON','multiRow':False,'columns':[
                    {'name':'seed_version','type':'String','length':50,'mandatory':True},
                    {'name':'source_country','type':'String','length':100,'mandatory':True},
                    {'name':'fixture_fields','type':'String','length':1000,'mandatory':True}]})

    def ensure_gender_values(self):
        codes=self.api('GET','/codes')
        matches=[c for c in codes if c['name']=='Gender']
        if len(matches)!=1:
            raise RuntimeError('Gender catalog is not uniquely identified')
        path='/codes/'+str(matches[0]['id'])+'/codevalues'
        values={v['name']:v['id'] for v in self.api('GET',path)}
        for name in ['Male','Female','Unknown - anonymized export']:
            if name not in values:
                result=self.api('POST',path,{'name':name,'position':len(values)+1,
                    'description':'Local anonymized demo import category; original source fields are preserved','isActive':True})
                # This fork's command result can identify the parent catalog, not
                # the new value. Resolve the actual value IDs from the read API.
                values={v['name']:v['id'] for v in self.api('GET',path)}
                if name not in values:
                    raise RuntimeError('New local code value was not returned by its catalog')
        return values

    def cohort_clients(self):
        template=self.api('GET','/clients/template')
        office=template.get('officeId')
        if office!=1:
            raise RuntimeError('Unexpected office template; review local office mapping')
        if template.get('isAddressEnabled') is not False:
            raise RuntimeError('Address processing changed; review the demo fixture before importing')
        genders=self.ensure_gender_values()
        surveys={kind:{(r['country'].strip(),r['client_id'].strip()):r for r in self.data[kind]['rows']}
            for kind in ['baseline','endline']}
        for number,client in enumerate(self.cohort,1):
            body={'officeId':office,'firstname':'Anonymized','lastname':client['code']+f'{client["ordinal"]:04}',
                'externalId':client['external_id'],'active':False,'legalFormId':1,'locale':'en','dateFormat':'yyyy-MM-dd',
                'submittedOnDate':self.args.import_date.isoformat()}
            observed={r[h].strip() for r in client['investments'] for h in ['gender','gender__2'] if r[h].strip()}
            gender=next(iter(observed)) if len(observed)==1 and observed.issubset({'Male','Female'}) else 'Unknown - anonymized export'
            body.update({'dateOfBirth':'2000-01-01','genderId':genders[gender],
                'address':[{'addressLine1':'DEMO ONLY - exact address absent from anonymized export'}]})
            fixture_fields={'dateOfBirth':'2000-01-01 IS FICTIONAL; exclude from source-age analysis',
                'display_name':'Generated anonymized demo label','legal_form':'PERSON demo shell',
                'client_status':'Pending demo import, not inferred source status',
                'address':'Fictional API placeholder; address storage is disabled in this local profile',
                'gender':'Mapped only when source values agree; otherwise explicitly unknown'}
            payload_sha=digest(stable(body).encode())
            prior=self.sql(f'SELECT payload_sha FROM {SCHEMA}.cohort_manifest WHERE external_id={literal(client["external_id"])};',True)
            if prior and prior!=payload_sha:
                raise RuntimeError('Existing cohort payload changed; refuse silent updates')
            found=self.api('GET','/clients?'+urllib.parse.urlencode({'externalId':client['external_id']}))['pageItems']
            if len(found)>1:
                raise RuntimeError('Duplicate external ID already exists in the local tenant')
            if found:
                if found[0].get('firstname')!='Anonymized' or found[0].get('lastname')!=body['lastname'] or found[0].get('officeId')!=office:
                    raise RuntimeError('Existing client does not match this demo import identity')
                client_id=found[0]['id']; self.summary['api_clients_reused']+=1
            else:
                result=self.api('POST','/clients',body)
                client_id=result.get('clientId') or result['resourceId']
                self.summary['api_clients_created']+=1
            ref=client['survey_key']
            values=[client['external_id'],client['key'][0],client['key'][1],ref[1] if ref else None,
                client_id,payload_sha,'client-created']
            self.sql(f'INSERT INTO {SCHEMA}.cohort_manifest VALUES('+','.join(map(literal,values))+
                ') ON DUPLICATE KEY UPDATE fineract_client_id=VALUES(fineract_client_id),import_state=VALUES(import_state);')
            client['fineract_id']=client_id
            provenance={'seed_version':'anonymized-export-demo-v1','source_country':client['key'][0],
                'fixture_fields':stable(fixture_fields)}
            existing_provenance=self.api('GET',f'/datatables/anon_seed_provenance/{client_id}?genericResultSet=false',allow_missing=True) or []
            if existing_provenance:
                if len(existing_provenance)!=1 or any(existing_provenance[0].get(k)!=v for k,v in provenance.items()):
                    raise RuntimeError('Existing fixture provenance differs; refuse an unmarked synthetic identity')
            else:
                self.api('POST',f'/datatables/anon_seed_provenance/{client_id}',{**provenance,'locale':'en'})
            for kind,table in self.data.items():
                rows=client['investments'] if kind=='investment' else ([surveys[kind][ref]] if ref in surveys[kind] else [])
                name='anon_seed_'+kind
                existing=self.api('GET',f'/datatables/{name}/{client_id}?genericResultSet=false',allow_missing=True) or []
                by_key={r['source_key']:r for r in existing}
                for row in rows:
                    source_key=table['sha']+':'+str(row['_source_row'])
                    entry={'source_key':source_key,'source_sha256':table['sha'],'source_row':row['_source_row']}
                    entry.update({col:value.strip() or None for col,value in zip(table['columns'],row['_values'])})
                    if source_key in by_key:
                        for col,value in entry.items():
                            if str(by_key[source_key].get(col))!=str(value):
                                raise RuntimeError('Existing snapshot differs from source mapping; do not overwrite')
                        self.summary['api_snapshot_rows_reused'][kind]+=1
                    else:
                        self.api('POST',f'/datatables/{name}/{client_id}',{**entry,'locale':'en'})
                        self.summary['api_snapshot_rows_created'][kind]+=1
            self.sql(f'UPDATE {SCHEMA}.cohort_manifest SET import_state="complete" WHERE external_id={literal(client["external_id"])};')
            if number==1 or number%20==0:
                print(f'API cohort clients and linked source observations complete: {number}/100',flush=True)

    def reconcile(self):
        expected={'investment':sum(len(c['investments']) for c in self.cohort),
            'baseline':sum(c['survey_key'] is not None for c in self.cohort),
            'endline':sum(c['survey_key'] is not None for c in self.cohort)}
        count=self.sql(f'SELECT COUNT(*) FROM {SCHEMA}.cohort_manifest WHERE import_state="complete";',True)
        if int(count)!=100:
            raise RuntimeError('Cohort reconciliation failed')
        for kind in self.data:
            actual=int(self.sql(f'SELECT COUNT(*) FROM fineract_default.anon_seed_{kind} d JOIN '
                f'{SCHEMA}.cohort_manifest c ON c.fineract_client_id=d.client_id;',True))
            if actual!=expected[kind]:
                raise RuntimeError('Linked API observation reconciliation failed')
        # Prove source-attribute copies match the exact staged row, allowing only documented trim/empty normalization.
        for kind,table in self.data.items():
            for col in table['columns']:
                mismatches=self.sql(f'SELECT COUNT(*) FROM fineract_default.anon_seed_{kind} d JOIN {SCHEMA}.raw_{kind} s '
                    'ON s._source_sha=d.source_sha256 AND s._source_row=d.source_row '
                    f'WHERE NOT (BINARY d.`{col}` <=> BINARY NULLIF(TRIM(s.`{col}`),""));',True)
                if int(mismatches):
                    raise RuntimeError('Mapped observation field differs from staging: '+kind+'/'+col)
        self.summary.update({'cohort_clients':100,'cohort_country_counts':dict(Counter(c['key'][0] for c in self.cohort)),
            'linked_observations':expected,'staging_schema':SCHEMA,'fineract_tenant':'default',
            'source_fingerprints':{k:v['sha'] for k,v in self.data.items()},'import_date':self.args.import_date.isoformat(),
            'fineract_clients_are_pending_demo_records':True,'financial_snapshots_are_not_live_ledger_loans':True})
        self.summary['mandatory_identity_placeholders']='DOB and API address input explicitly marked fictional in anon_seed_provenance; not source observations'
        (self.state/'reconciliation.json').write_text(json.dumps(self.summary,indent=2)+'\n')
        print('PASS: full source staging, 100-client API cohort and all attached source attributes reconciled.',flush=True)
        print(json.dumps(self.summary,indent=2),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--username',default='mifos')
    parser.add_argument('--import-date',type=date.fromisoformat,default=date(2026,10,20))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--demo-required-fields',action='store_true',help='Explicitly tag fictional DOB/address inputs required for demo PERSON shells')
    parser.add_argument('--stage-only',action='store_true',help='Load/reconcile source staging without creating client shells')
    args=parser.parse_args()
    if args.apply and not args.stage_only and not args.demo_required_fields:
        parser.error('Client shells require --demo-required-fields; use --stage-only to retain source staging only')
    data=load_sources(args.source); cohort=choose_cohort(data)
    print(json.dumps({'source_rows':{k:len(t['rows']) for k,t in data.items()},'cohort_clients':len(cohort),
        'cohort_country_counts':dict(Counter(c['key'][0] for c in cohort)),
        'cohort_with_unambiguous_survey_links':sum(c['survey_key'] is not None for c in cohort),'apply':args.apply}),flush=True)
    if not args.apply:
        print('Dry run only. No API or database writes.'); return
    seeder=Seeder(args,data,cohort)
    seeder.api('GET','/offices')
    seeder.stage()
    if args.stage_only:
        return
    seeder.ensure_datatables(); seeder.cohort_clients(); seeder.reconcile()

if __name__=='__main__':
    main()
