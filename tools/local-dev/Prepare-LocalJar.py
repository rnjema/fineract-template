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

"""Create an explicitly patched LOCAL-DEMO JAR; never edit the source checkout.

The fork's language-report changeset assumes production report id 216.
An empty demo database creates Loan Due in X days with a different id.
Preserve the already-executed changesets, add a corrective report-name update,
and repair only the not-yet-executed report-parameter mapping.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, zipfile
import xml.etree.ElementTree as ET

p=argparse.ArgumentParser()
p.add_argument('--activate',action='store_true',help='Update only FINERACT_JAR in the existing private local env file')
p.add_argument('--source', help='Explicit path to the original, unpatched executable JAR')
args=p.parse_args()
root=Path(__file__).resolve().parent
env=root/'.env.local'
text=env.read_text(encoding='utf-8-sig')
m=re.search(r"^FINERACT_JAR='([^']+)'\s*$",text,re.M)
if not m: raise SystemExit('Expected initialized single-quoted FINERACT_JAR entry.')
source=Path(args.source) if args.source else Path(m.group(1))
state=root/'.runtime'; state.mkdir(exist_ok=True)
dest=state/'fineract-provider-capstone-local.jar'
record=state/'local-jar-patch.json'
if source.resolve()==dest.resolve():
 if not record.exists(): raise SystemExit('Patch record missing; specify the original artifact before proceeding.')
 previous=json.loads(record.read_text())
 source=Path(previous['original_jar'])
name='BOOT-INF/classes/db/changelog/tenant/custom-changelog/CGLT-431_add_language_parameter.xml'
with zipfile.ZipFile(source) as z:
 if any(n.startswith('META-INF/') and n.upper().endswith(('.SF','.RSA','.DSA')) for n in z.namelist()):
  raise SystemExit('Signed outer archive: do not modify; rebuild from a reviewed source change instead.')
 original=z.read(name).decode('utf-8')
 mapping_id='add-language-parameter-mapping-216-fix'
 match=re.search(r'    <changeSet id="'+mapping_id+r'".*?</changeSet>',original,re.S)
 if not match: raise SystemExit('Expected migration shape not found; manual review required.')
 update_match=re.search(r'        <update tableName="stretchy_report".*?</update>',original,re.S)
 if not update_match: raise SystemExit('Expected report SQL update not found.')
 update=update_match.group(0).replace('<where>id = 216</where>',"<where>report_name = 'Loan Due in X days'</where>")
 if update==update_match.group(0): raise SystemExit('Expected hard-coded update predicate not found.')
 corrective='''    <changeSet id="capstone-local-correct-language-report-by-name-v1" author="capstone-local-only">
        <preConditions onFail="HALT">
            <sqlCheck expectedResult="1">SELECT COUNT(*) FROM fineract_default.stretchy_report WHERE report_name = 'Loan Due in X days'</sqlCheck>
        </preConditions>
'''+update+'''
    </changeSet>
'''
 mapping='''    <changeSet id="add-language-parameter-mapping-216-fix" author="niceta@inkomoko.com">
        <preConditions onFail="HALT">
            <sqlCheck expectedResult="1">SELECT COUNT(*) FROM fineract_default.stretchy_report WHERE report_name = 'Loan Due in X days'</sqlCheck>
            <sqlCheck expectedResult="1">SELECT COUNT(*) FROM fineract_default.stretchy_parameter WHERE parameter_name = 'language'</sqlCheck>
        </preConditions>
        <sql>
            INSERT INTO fineract_default.stretchy_report_parameter (report_id, parameter_id, report_parameter_name)
            SELECT r.id, p.id, 'language'
            FROM fineract_default.stretchy_report r
            CROSS JOIN fineract_default.stretchy_parameter p
            WHERE r.report_name = 'Loan Due in X days'
              AND p.parameter_name = 'language'
              AND NOT EXISTS (
                  SELECT 1 FROM fineract_default.stretchy_report_parameter rp
                  WHERE rp.report_id = r.id AND rp.parameter_id = p.id
              );
        </sql>
    </changeSet>'''
 patched=original[:match.start()]+corrective+mapping+original[match.end():]
 ET.fromstring(patched)
 root_name='BOOT-INF/classes/db/changelog/tenant/changelog-tenant.xml'
 root_original=z.read(root_name).decode('utf-8')
 dependency='    <include file="parts/FSI-187_add_crb_transunion_logger_details.xml" relativeToChangelogFile="true"/>'
 custom='    <includeAll path="custom-changelog" relativeToChangelogFile="true"/>'
 if root_original.count(dependency)!=1 or root_original.count(custom)!=1:
  raise SystemExit('Unexpected tenant changelog shape; review dependency ordering manually.')
 approval_dependency='    <include file="custom-changelog/INKO-276-update-icreview-approval-form.xml" relativeToChangelogFile="true"/>'
 odoo_dependency='    <include file="custom-changelog/inko_174_add_odoo_journal_entry_details_in_Journal_entry_table.xml" relativeToChangelogFile="true"/>'
 provisioning_base='    <include file="custom-changelog/CGLT_84_add_loans_to_loan_product_provisional_entries.xml" relativeToChangelogFile="true"/>'
 provisioning_dynamic='    <include file="custom-changelog/CGLT_537_dynamic_provisioning_categories.xml" relativeToChangelogFile="true"/>'
 root_patched=root_original.replace(dependency,'').replace(custom,'\n'.join([dependency,approval_dependency,odoo_dependency,provisioning_base,provisioning_dynamic,custom]))
 cashflow_name='BOOT-INF/classes/db/changelog/tenant/custom-changelog/INKO-293-update-error-message-and-validate-against-auto-computed-recommended-amount.xml'
 cashflow_original=z.read(cashflow_name).decode('utf-8')
 cashflow_patched=cashflow_original.replace('        <dropForeignKeyConstraint', '''        <preConditions onFail="MARK_RAN">
            <foreignKeyConstraintExists foreignKeyName="FK_m_loan_repayment_schedule_cashflow" foreignKeyTableName="m_loan_cashflow_projection"/>
        </preConditions>
        <dropForeignKeyConstraint''',1)
 if cashflow_patched==cashflow_original: raise SystemExit('Unexpected cashflow migration shape.')
 cashflow_include='    <include file="custom-changelog/INKO-293-update-error-message-and-validate-against-auto-computed-recommended-amount.xml" relativeToChangelogFile="true"/>'
 drop_include='    <include file="parts/INKO-308-drop-repayment-schedule-foriegn-key-from-cashflow.xml" relativeToChangelogFile="true" />'
 if root_patched.count(drop_include)!=1: raise SystemExit('Expected cashflow removal include missing.')
 root_patched=root_patched.replace(drop_include,cashflow_include+'\n'+drop_include)
 ET.fromstring(cashflow_patched)
 ET.fromstring(root_patched)
 # Existing executed changesets must remain byte-identical; do not clear checksums.
 assert patched.startswith(original[:match.start()])
 temp=dest.with_suffix('.tmp.jar')
 with zipfile.ZipFile(temp,'w') as out:
  for info in z.infolist():
   if info.filename==name: out.writestr(info,patched.encode('utf-8'))
   elif info.filename==root_name: out.writestr(info,root_patched.encode('utf-8'))
   elif info.filename==cashflow_name: out.writestr(info,cashflow_patched.encode('utf-8'))
   else:
    with z.open(info) as src, out.open(info,'w') as dst: shutil.copyfileobj(src,dst,1024*1024)
 temp.replace(dest)
report={'scope':'LOCAL DISPOSABLE DEMO ONLY; not an upstream or production migration fix',
 'original_jar':str(source),'original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'patched_jar':str(dest),'patched_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
 'resources':[name,root_name,cashflow_name],'changes':'Preserve executed changesets; resolve report by name; order logger, approval, Odoo and provisioning dependencies; run INKO-293 before INKO-308, guarding the obsolete replacement if INKO-308 already removed the foreign key',
 'database_changelog_manually_changed':False,'source_checkout_changed':False}
record.write_text(json.dumps(report,indent=2)+'\n')
if args.activate:
 new="FINERACT_JAR='"+dest.as_posix()+"'"
 env.write_text(text[:m.start()]+new+text[m.end():],encoding='utf-8')
print('Prepared local-only JAR and patch record. Original artifact preserved.')
print('Local-only artifact SHA256:',report['patched_sha256'])
