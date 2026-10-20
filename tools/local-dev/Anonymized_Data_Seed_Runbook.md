# Seed the local workbench from the existing anonymized data

**Later approved extension, 20 October:** these 100 shells now have a synthetic PII overlay and 30 explicitly generated loan histories. The source staging and attached observations described below are unchanged. See [Synthetic_PII_Testbed_Runbook.md](Synthetic_PII_Testbed_Runbook.md). Do not rerun this original importer to overwrite the new identities or provenance; its conflict checks intentionally refuse that operation. Its counts and zero-loan result below document the original import stage.

**Date:** 20 October 2026. **Approved scope:** full source staging plus a 100-client Fineract demonstration cohort, selected explicitly by the user. **Target:** the existing isolated local MariaDB/Fineract workbench only. No production connection or native additional tenant is involved.

**Completed and reconciled:** all 52,972 source rows are staged; 100 pending demo clients were created with 120 investment, 75 baseline and 75 endline observations, plus one provenance entry per client. Every attached source field matches its staged value under the documented normalization. Browser authentication, client listing and create-client template reads returned HTTP 200 after the import. This verifies API-created clients; manual form submission and a banking loan lifecycle remain separate checks.

## What is being loaded

The three files in the EWS clone's `ml/Anomynized data/Anomynized data/Anomynized data/` directory are the source. Generated `synthetic_outputs` and the earlier 22-client synthetic proposals are not used for this import.

| Source | Rows | Local staging table |
| --- | ---: | --- |
| Baseline business surveys | 8,976 | `capstone_anonymized_seed.raw_baseline` |
| Endline business surveys | 8,976 | `capstone_anonymized_seed.raw_endline` |
| Investment snapshots | 35,020 | `capstone_anonymized_seed.raw_investment` |
| Total | 52,972 | All original source rows retained |

Each staging row includes the source-file SHA256, original CSV row number, a canonical array of original cell values and its SHA256. Source fields are also stored as separate text columns with `src_` prefixes. Numeric/date strings and blanks are preserved without floating-point conversion, currency assumptions or date reinterpretation. Headers and decoder choices are recorded in `seed_files`; the two survey files decode as CP1252 and the investment file as UTF-8 with optional BOM handling. The source files are unchanged.

The investment CSV has two `gender` headers. They remain distinct as `src_gender` and `src_gender_2`. No row is discarded merely because its loan number repeats. There are 33,459 distinct country/loan-number pairs across 35,020 rows; these snapshots are not assumed to have unique ledger-account keys.

## What appears in Fineract

The demo uses 25 investment-client identities from each country: Rwanda, Ethiopia, South Sudan and Kenya. Selection is deterministic and balanced for demonstration; it is not a statistically representative sample. It prefers explicit survey references that are unambiguous in both directions. The selected 75 Rwanda/Ethiopia/South Sudan clients have such links; the 25 Kenya clients do not have surveys in these files.

Clients are created through the Fineract API in tenant `default`, using the existing head office. Their local display labels are `Anonymized RW0001`, etc., with deterministic, country-scoped external IDs. They are pending PERSON demo shells created on the import date, not inferred historical activation dates or certified source legal-form/status values.

This fork requires a birth date and a non-empty address input for PERSON clients, while the export provides no exact birth date/address. With the explicit `--demo-required-fields` mode, the shell uses **fictional DOB 2000-01-01** and a labeled fictional address input. The current profile disables address storage, so the placeholder is not a claimed physical address record. `anon_seed_provenance` marks these fixture fields for every client. Source ages and locations are unchanged; **do not derive analytical age from these shell birthdays**. Gender is mapped only when source values consistently agree; missing/conflicting values map to an explicitly unknown local category. Missing Female/Unknown catalog values are created locally, with their actual IDs resolved from the read API. Original gender columns remain intact in the source datatables.

Three multi-row source datatables and one provenance datatable are registered against `m_client` through the supported API:

- `anon_seed_investment`: all investment rows for selected banking client identities.
- `anon_seed_baseline`: matched baseline observations.
- `anon_seed_endline`: matched endline observations.
- `anon_seed_provenance`: one-row metadata marking generated identity/required-field fixtures.

They carry source hashes/row numbers and the source attributes. UI copies trim surrounding whitespace and represent empty fields as null; the full original values remain in staging. The import verifies each attached field against staging under that normalization. In the community app, open **Clients**, select an `Anonymized ...` client and inspect its registered datatable entries. A browser reload may be needed for newly registered tables to appear.

**These are not live Fineract ledger loans.** The files contain cumulative payments/balances and snapshots, but not a complete dated transaction ledger, confirmed product terms or an explicit currency field. No native loans, repayments, interest calculations, write-offs or business records are fabricated. The normal Loans tab can therefore remain empty even when investment snapshot entries exist. This workbench supports identity linkage and observation extraction; full lifecycle generation is still a separate, clearly synthetic exercise.

## Relationships and tenancy

Banking `ClientId` and survey `client_id` have zero direct country/ID overlap. Investment `BaselineEndlineClientId` is the explicit bridge: 2,679 distinct references match survey keys; four do not. Missing or ambiguous links remain unresolved rather than being guessed.

`capstone_anonymized_seed.cohort_manifest` maps the selected country/banking identity to the new Fineract client ID and, where safe, the survey identity. This is a restricted lineage table, not an analyst-safe export. Country is a source attribute, not a newly provisioned Fineract tenant. The native tenant remains `default`. This import does not resolve the previously identified hard-coded-schema migration issue.

## Run or resume

First start the committed backend profile and the community frontend as described in `Inkomoko_Demo_Workbench_Runbook.md`. The import has a fixed loopback API target on port 9002 and a fixed local DB container. It does not accept a production URL.

From this runbook directory, use Python 3:

```powershell
python .\test_anonymized_seed.py
python .\Seed-AnonymizedWorkbench.py
python .\Seed-AnonymizedWorkbench.py --apply --demo-required-fields
```

The command without `--apply` only validates source structure and the cohort; it makes no network/database writes. `--apply --stage-only` loads/reconciles source staging without client shells. The full cohort requires the explicit fixture flag; it will not silently invent required identity fields. Use `--source 'PATH_TO_THE_THREE_CSVS'` if the input directory moves. The fresh demo username defaults to `mifos`; a non-default password can be provided privately through the `LOCAL_DEMO_PASSWORD` process environment. Never put it in command arguments, logs or this document.

The fixed default import date is 20 October 2026. Keep it unchanged when resuming this import. A different date changes the client payload hash and is deliberately refused for existing mappings; design a separate import version rather than silently updating prior records.

Resume behavior:

1. File hashes are matched to their names. Changed input under an existing file name is rejected for review.
2. Raw rows use the source-file hash and original row number as a primary key. Completed source tables are count/hash checked and reused.
3. Clients are looked up by deterministic external ID before creation. An existing identity with a different local name/office or changed payload is refused rather than overwritten.
4. Observation rows have globally unique source keys. Existing rows are compared with the source mapping before reuse. No blanket POST retry or record deletion is used.
5. A partial failure leaves completed staging and client mappings intact. Correct the named issue and rerun the same command; do not drop schemas or reset the volume.

This fork rejects a `unique` field option in the datatable creation API. Tables are created through that API; a unique source-key index is then added directly only to these newly owned demo extension tables. No core banking ledger table is directly inserted or altered.

## Reconciliation and evidence

The completed second import reused all 100 clients and 270 observations, created zero additional clients/observations, and passed the same source-field reconciliation. Three focused importer unit checks also passed. Aggregate execution evidence is recorded in `validation-20261020.json`; original private execution summaries remain under `.runtime/anonymized-seed/`.

Successful execution prints aggregate counts only and saves `.runtime/anonymized-seed/reconciliation.json`. Database/API error bodies, if needed for diagnosis, are saved privately in that ignored directory and are not printed with source records.

Acceptance requires all source row counts and payload hashes to reconcile; exactly 100 completed cohort mappings; the expected observation counts; and zero differences between attached source fields and staged values. Rerunning should create zero new clients or observation rows. Runtime evidence, source values and lineage mappings must stay out of Git and the public reproduction pack.

The source data is described as anonymized, but still contains locations, demographics and financial observations. This import does not independently certify anonymization or implement the planned de-identification policy. Restrict the local staging/lineage data and use the established extraction/de-identification release gates before sharing an analyst dataset.
