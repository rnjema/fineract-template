# Isolated local Fineract development runtime

This profile records the setup used to run the September 2026 Inkomoko development snapshot locally. It runs MariaDB 10.8 and the existing executable Fineract JAR under Java 17. The community frontend lives in the sibling `community-app-template` clone and uses its `tools/local-dev/server.cjs` profile on port 9002.

The Compose project is `capstone-fineract-local`; its database volume is `capstone-fineract-local_capstone_db`. This is a disposable local demo, not a copy of Inkomoko production. No seeding is performed. Backend port 8443 binds only to `127.0.0.1`; the database has no published host port. The unused Kafka outcome consumer is disabled, and backend logs rotate at 10 MB x 3.

## Start

Use Docker Desktop, PowerShell 7 and Python 3. From this directory:

```powershell
.\Initialize-Local.ps1 -JarPath 'FULL_PATH_TO_REVIEWED_EXECUTABLE.jar'
python .\Prepare-LocalJar.py --activate
.\Start-Backend.ps1
.\Test-LocalApi.ps1
```

For the already initialized local database, **preserve the original `.env.local` password**. This machine's working configuration has been privately carried over from the capstone runbook. The password, runtime JAR and patch record are ignored and must not be committed. Initialization refuses to invent a new password when it detects the existing demo volume. Restore the original private env file instead. Do not delete or reset that volume to resolve a configuration issue.

The selected original artifact was `fineract-provider-0.0.0-bf9cc511.jar`, SHA256 `5bd179ccda7069609512e0a1ae078667afe23a4664484fe51153c6de791e2202`. It was reused to avoid rebuilding the large source tree under disk/memory pressure. This is not evidence that all later working-tree edits were compiled. Keep Java 17, static weaving and the fork's build flags when rebuilding separately.

`Prepare-LocalJar.py` creates a separate local-only JAR, preserves the original, and records hashes. `--activate` changes only `FINERACT_JAR` in the private env file. If the env file already selects a patched artifact outside this directory, supply the original explicitly with `--source FULL_PATH_TO_ORIGINAL.jar`. Do not repatch an already patched JAR as if it were the original.

The helper addresses observed fresh-database defects without modifying backend source or manually clearing Liquibase checksums/history:

- Resolve **Loan Due in X days** and the language parameter by name instead of assuming report ID 216. Preserve the already-run changesets and add a corrective report update.
- Include FSI-187 logger creation before CGLT-476 alters the consumer logger.
- Include INKO-276 approval columns before CGLT-496 migrates them.
- Include inko_174 Odoo columns before CGLT-606 adds its index.
- Include CGLT_84 provisioning snapshots, then CGLT_537 dynamic columns, before dependent migrations.
- Order INKO-293 cashflow foreign-key replacement before INKO-308 removal. Guard the obsolete replacement when the later removal has already run on the partially initialized demo.

Exactly three migration resources differ in the tested patched artifact, SHA256 `7e2a716a09e5716d3b686cc4b89de698e8cddd7fdf0b3ebb1d399f2a8ec9ca16`. A complete migration run and restart succeeded against the local demo, followed by direct and proxied authenticated reads. A from-zero replay of the final patch and production migration compatibility have not been established. Promote reviewed source migrations separately; this helper is not a production repair.

First startup or a cached restart may take three minutes. Wait for `Started ServerApplication`, then test; an open port is insufficient. The preflight uses 8 GiB of system-drive headroom; allow at least 15 GiB before initial image pulls. It does not delete files. Avoid large rebuilds when disk space is low.

## Community frontend and verification

In the community clone, run `node tools/local-dev/server.cjs`, then open:

<http://127.0.0.1:9002/?baseApiUrl=http://127.0.0.1:9002&tenantIdentifier=default>

For the fresh local demo, login is `mifos` / `password`, tenant `default`. Validate through that frontend's proxy with:

```powershell
.\Test-LocalApi.ps1 -BaseUrl 'http://127.0.0.1:9002'
```

Browser verification on 18 October 2026 passed login, client-list loading and the create-client form's backend template request. No client was saved. The modern Angular sandbox on port 4200 is optional and separate. These snapshots have not been certified as the release currently served by Inkomoko.

## Stop safely

```powershell
docker compose --project-name capstone-fineract-local --env-file .env.local -f compose.yaml stop
```

This preserves the database. Do not add destructive volume-removal flags. Do not run the fork's production workflows or data-correction scripts for local startup. Existing source/build/CI changes outside this profile are intentionally excluded from the local-setup commit.

## Source staging and synthetic PII fixtures (20 October 2026)

The approved workbench now contains the source-based 100-client cohort and a synthetic identity/loan overlay. See [Synthetic_PII_Testbed_Runbook.md](Synthetic_PII_Testbed_Runbook.md) for current counts, guided Faker generation, backup/restore verification, loan-schema compatibility, repeat execution and a private evaluation answer key. [Anonymized_Data_Seed_Runbook.md](Anonymized_Data_Seed_Runbook.md) documents the initial source load; it should not overwrite the later PII overlay. Startup commands above do not themselves seed data.

The executed fixture state currently lives at `D:\GradSchool\CMU\04950 - Engineering AI Capstone\docs\engineering\local-fineract\.runtime\pii-testbed`, alongside the executed tooling. This commit contains reusable public source only. Run verify/replay from that original directory for this running instance. When transferring the instance, preserve the matching private state/configuration separately; a newly cloned tools directory cannot safely resume by guessing missing before-images or command history. For a new source-based demo, install the pinned Faker dependency in this directory's ignored `.runtime/pii-deps` and follow the fixture runbook. Source CSVs, generated identities, backups and the answer key are excluded from Git.
