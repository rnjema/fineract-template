# Run the synthetic PII testbed

**Completed:** 20 October 2026. **Target:** the existing isolated Inkomoko-derived local development workbench, tenant `default`. This extends the approved source-based import; it does not reconstruct real customer identities or the original source loan ledger.

## What is running

Open <http://127.0.0.1:9002/?baseApiUrl=http://127.0.0.1:9002&tenantIdentifier=default> with the local demo login `mifos` / `password`. The community frontend proxies to Fineract HTTPS port 8443. See [the startup runbook](Inkomoko_Demo_Workbench_Runbook.md) to restart the same instance and preserve its volume/private configuration.

| Fixture | Verified count |
| --- | ---: |
| Existing clients with synthetic identities | 100 |
| Regional / global name profiles | 80 / 20 |
| Registered contact/business-text fixture entries | 100 |
| Client notes / loan notes / transaction notes | 100 / 30 / 92 |
| Loan applications | 30 |
| Disbursements / repayments | 26 / 66 |
| Scheduled installments | 180 |
| Original baseline / endline / investment staging rows | 8,976 / 8,976 / 35,020 |
| Original attached observations, unchanged | 270 |
| Planted occurrence annotations in private answer key | 3,726 |
| Additional malformed ingestion cases, file-only | 5 |

The 30 loans include the successful pilot. Ten are fully repaid on their schedules, ten are overdue without repayments, six have a USD 25 partial repayment and a remaining overdue balance, and four are approved but undisbursed. The dedicated synthetic USD product has zero interest, six monthly installments and USD 600 principal per application. Total disbursement is USD 15,600; repayments total USD 6,150. These are API-created local ledger fixtures, not movements of real money or an inferred source history.

## Inspect in the community app

Reload the Clients page to replace the old `Anonymized ...` display labels with realistic names. The 100 client IDs and source links are unchanged. Open a client and inspect its native name, synthetic birth date, phone, notes and `pii_fixture_contact` datatable. That table contains a person name in a business label, a phone embedded in a location, a fictional identity number, next-of-kin contact and serialized JSON containing more identifiers. Notes contain aliases, repeated identifiers and mixed formatting.

Only the 30 clients selected for loan cases are activated; the other 70 remain pending. A client without a fixture loan will still have identity, contact and note test coverage. Loan and transaction notes repeat PII deliberately. Native addresses and native business records were not populated; the registered contact/business-text datatable is the explicitly labeled supported fallback. Single-name, malformed and very long values are in file-only stress cases, not represented as accepted native records.

The regional provider combines curated given-name and family/patronymic examples independently for Rwanda, Ethiopia, South Sudan and Kenya. It includes punctuation and Unicode, plus global Faker locale profiles. These examples are not a demographic model or authoritative naming rules. Generated names, birthdays and financial history are independent of imported observations. Native gender/source demographics were not inferred from names.

Names and phones remain intact in raw input. Synthetic ownership is recorded separately so the detector cannot succeed merely by finding a `SYNTHETIC` prefix in every name. Email uses `example.org`. Fictional national IDs currently use a `TST-...` format; add further policy-specific ID-format cases in a new fixture version if required. Phone strings are not certified unassigned; do not contact them.

## Files and private state

Run these commands from this directory. Python, Docker Desktop, the existing source import and both running services are prerequisites.

```powershell
python -m pip install --target .runtime/pii-deps -r requirements-pii.txt
python -m unittest discover -s . -p 'test_pii*.py'
python .\Seed-PIITestbed.py verify
```

- `pii_fixture.py`: pinned, seeded Faker and curated regional provider.
- `Seed-PIITestbed.py`: fixed local target, backup/restore rehearsal, journaled API import and replay.
- `pii_verification.py`: stored-field, loan-scenario and source-preservation reconciliation.
- `pii_release.py`: a known-planted-identifier leakage smoke check for JSON release artifacts.
- `.runtime/pii-testbed/`: restricted backup, immutable fixture, before-images, command journal, raw extraction, answer key and reports. This ignored directory must not be committed or included in analyst releases.

The generated fixture is frozen in `fixture.json` with `fixture.sha256`; Faker 40.43.0 and tzdata 2026.5 are pinned for new generation. Per-client random streams keep generation independent of input ordering. Do not edit the saved fixture or a completed command's payload. Preserve the whole private state folder with its matching workbench backup/configuration when handing the instance to another operator.

## Reproduce from the original source-based demo

On the existing overlaid instance, use `verify` or repeat `apply` with its preserved state. Do not rerun the original anonymized importer to undo this overlay: its identity/provenance checks intentionally refuse changed shells.

For a genuinely original 100-shell source-based demo, run the initial import according to [Anonymized_Data_Seed_Runbook.md](Anonymized_Data_Seed_Runbook.md), then:

```powershell
python .\Seed-PIITestbed.py backup
python .\Seed-PIITestbed.py generate
python .\Seed-PIITestbed.py apply --pilot
python .\Seed-PIITestbed.py apply
python .\Seed-PIITestbed.py verify
```

`backup` saves all three local workbench schemas and restores them into a temporary MariaDB container using the already cached image, no network and RAM-backed storage. The readiness check waits for completion of MariaDB initialization, not its intermediate temporary server. Restored source/client/loan counts must match before writes proceed. The temporary container is stopped after the rehearsal; its data is disposable. The active workbench is never replaced by that operation.

Preflight found a seeded active loan-email hook. Its configuration was captured privately and it was disabled through the API before identities or loans were changed. It remains disabled in this PII testbed. Do not enable notification, payment or external verification integrations for these fixtures.

## Fork-specific compatibility and recovery

This fork requires the unchanged `externalId` even on client updates; loan product `allowableDSCR`; explicit loan description, fund, department, purpose and `applicationDate`; and a payment-type selection during approval. The importer discovers catalog IDs rather than assuming IDs returned by creation refer to newly created code values.

The running loan entity also maps `m_loan.office_id`, which was absent from this migrated demo table. After the verified backup and while the loan table was empty, the runner added a nullable BIGINT office reference and a foreign key to `m_office`. This is a documented local schema compatibility correction. It is not an upstream migration repair; no Liquibase history or original JAR was changed, and no core ledger rows were inserted directly. Keep `loan-schema-compatibility.json` with private runtime evidence. Reproduce this correction through the runner, not an undocumented database edit.

Client submission/activation dates were set to generated April 2026 dates to permit valid historical synthetic loan commands. Before-images preserve the original shell values. Updated `anon_seed_provenance` labels these dates and all generated identity fields. Source staging and the three observation datatables retain their original checksums.

Every mutating request journals its intended payload before sending. Completed commands are reused, and a changed completed payload is rejected. A timeout or ambiguous server outcome leaves the command pending; the runner refuses a blind financial retry. Reconcile by external ID, transaction ID, actual schedules/balances and server evidence before repairing a pending journal entry. Never delete the journal to bypass this guard. Definite request rejections can be corrected and retried; successful commands stay immutable.

If state is lost, recover the original private state and backup. A new 'before' backup is refused once fixture clients have changed. A full restore of the active workbench requires stopping its services and acknowledging that all changes after the backup boundary will be reverted. No automatic financial rollback is supplied; identity-only reversal is not reversal of loan transactions.

## Use as pipeline input and evaluate output

Verification writes `.runtime/pii-testbed/raw-extract.json` with 722 records spanning clients, fixture contacts, client notes, the original linked observations, loans, loan notes and transaction notes. It also writes the withheld `.runtime/pii-testbed/answer-key.json`. Keep the answer key separate from scanner input, policies, model prompts and analyst exports. API metadata/provenance is not an approved analytical release schema.

Point the extraction/de-identification development workflow at this local testbed or the restricted raw extraction. The existing engineering runbook's default policy drops free text from analyst releases; a retained-text redaction experiment is a separate mode. Treat quasi-identifiers, source IDs, joining keys and financial utility according to an approved release policy. Do not combine synthetic ledger outcomes with imported observations as though they describe the same historical borrower behavior.

Check an output JSON artifact with:

```powershell
python .\pii_release.py --release 'PATH_TO_PIPELINE_OUTPUT.json' --report .runtime/pii-testbed/release-check.json
```

The smoke check compares known planted values using case/Unicode/format normalization. It checks birth-date arrays and numeric values, and reports counts without printing leaked identifiers. It also checks 30 principal-value controls by fixture external ID. If the pipeline tokenizes those joining IDs, supply `--linkage-map PATH_TO_PRIVATE_JSON` with a mapping from original fixture loan external IDs to released tokens. Unmatched controls are reported as unjoinable rather than changed amounts. Unknown PII, quasi-identifier risk, detector false positives, clean-text false removals and token-linkage consistency are explicitly **not evaluated** by this smoke check. Clean text controls are supplied for a later scanner evaluation, not falsely scored as scanner accuracy here.

A raw-input positive control should report leakage. A deliberately identifier-free control can test that the harness accepts absence, but is not a working de-identification pipeline or evidence of privacy. No actual pipeline performance or anonymization certification is claimed by this fixture build.

**Completed verification:** the full repeat import executed zero new API mutations and left all six counted fixture/core tables unchanged. All command journal entries are complete. Nine focused tests passed. The raw-input harness check found all 892 distinct known planted values; an explicitly artificial identifier-free control found zero and matched all 30 principal controls. These are harness checks, not a de-identification accuracy result. Private execution evidence is in `verification.json`, `repeat-verification.json` and `harness-self-check.json` under the runtime folder.

## Resource note

C: was nearly full during this run. No images were downloaded or backend/client builds performed. The backup and fixture files live on D:, and the restore database used temporary RAM-backed storage. Recover disk headroom before builds, additional stacks or larger fixture cohorts; preserve the working database volume.
