# Synthetic PII testbed for extraction and de-identification

Prepared 20 October 2026. This is a proposed change to the existing local workbench; it has not been applied.

## Purpose and scope

The user wants realistic-looking identifying input, including East African and global names and PII in unexpected fields, to exercise extraction and de-identification. All new identity and banking lifecycle values will be synthetic. The existing anonymized exports remain unchanged. A fictional identity assigned to an imported observation is a test association, not a reconstruction of its original person.

The proposed default is to enrich the existing 100 demo shells rather than add another 100 clients. Keep their Fineract IDs, stable source links and original observation datatables. Save a before-image of every changed field, update provenance, and version the new importer independently of the original seed. The original seed's changed-payload checks must continue to refuse incompatible updates; its runbook will distinguish initial loading from the later PII overlay. There will be no automatic rollback of financial transactions or deletion of source records.

Only the fixed loopback workbench and tenant `default` are in scope. Country labels are source attributes; this does not provision additional native tenants or establish production parity.

## Guided Faker generation

Use Python Faker with its exact dependency version pinned, a fixed seed, and stable per-client random streams. Archive the generated fixture before applying it so repeat execution uses identical values. Use a custom provider with curated independent given-name and family-name pools for Kenyan/Swahili, Rwandan/Kinyarwanda, Ethiopian and South Sudanese examples, supplemented with other regional examples and global locale providers. These are plausible engineering fixtures, not statistically representative or authoritative naming models; do not force every naming tradition into a Western first/last pattern. Include single names, multiple given names, patronymic-style strings, hyphens, apostrophes and Unicode where the API permits them.

Default name mix: 80 East African regional profiles (20 per current source country) and 20 global profiles (five per country). A global-name fixture is an intentional test case, not an assertion about a source person's ethnicity. Names do not determine source demographics or gender. Generate plausible adult birth dates independently from imported source ages; preserve and label this distinction. Keep family/contact relationships and repeated aliases consistent across fields and entities.

Keep the realistic name/contact text intact as raw pipeline input. Do not prefix person names with 'SYNTHETIC' or mask the planted identifiers before extraction. Put fixture ownership/version labels in separate provenance; retain existing stable external IDs for recovery and source linkage. API limitations on name parts must be recorded; preserve unsupported full-name forms in the raw fixture rather than silently anglicizing them.

Email addresses use reserved example domains. National-ID/passport/mobile-money identifiers are fictional test formats with recorded validation limitations. Phone strings are synthetic, are not asserted to be unassigned, and must never be used to contact anyone. No notification, payment, document-upload or external verification integration will be enabled. Fully realistic contact formats belong only in this isolated testbed.

## Coverage and planted leakage

Create a coverage manifest for every client and each applied occurrence: entity, actual ID, field path, exact stored text, PII type, character span where appropriate, canonical synthetic identity, intended policy action, scenario and verification status. Do not put an expected-PII flag beside ordinary application fields where the detector could use it as a shortcut. Provenance is separate from the detector input.

| Location | Test cases |
| --- | --- |
| Native client name, DOB and supported contact fields | Regional/global names, date/phone formatting variants, accents, aliases |
| Supported client identifiers and addresses | Fictional identity numbers, street/landmark details and embedded contact text |
| Client notes | Borrower, guarantor and next-of-kin names; multiple people/phones in one note; multilingual or mixed-language text |
| Loan notes and payment/reference text where supported | Copied phone/ID/email/name, alternate formatting and repeated identity across client/loan records |
| Business descriptions and custom datatables | A person name in a business label, phone in an address or description, nested JSON serialized as text |
| Extraction stress fixture outside native fields | Very long notes, escaped newlines, encoded text, unusual Unicode and malformed records rejected by API validators |

Treat the user's 'runaway values' as both misplaced PII and unusual formatting, lengths and numeric outliers. Keep native typed fields valid. Put invalid dates, implausible ages/amounts and overlength strings in a separately tagged raw-ingest stress fixture; never coerce invalid values into real monetary/date columns or silently drop rejected cases. Record separately what was generated, what the API accepted, what was read back, and what remained file-only. File-only coverage is not database coverage.

Include clean control text, valid business names, ordinary dates, loan/account numbers and amounts that resemble identity strings. Expected treatment depends on the release policy: classify direct identifiers for stripping/tokenization, quasi-identifiers for approved generalization, and financial measures for retention or an explicitly documented privacy transformation. A name-looking word alone does not prove a leak. Synthetic values may coincidentally resemble real people; they are never sourced from real identities.

Align the baseline with the existing engineering runbook: free text is dropped from the default analyst release. Retained-text redaction is a separate evaluated mode; it is not silently substituted for that baseline. Keep both direct raw-identifier and quasi-identifier test coverage. Ground-truth scenario labels and provenance cannot substitute for discovery of unknown source fields.

## Synthetic banking lifecycle

The current instance has no loan products and its 100 seeded clients are pending. Discover required client activation, product, business and loan fields from this fork's source and API templates. First execute and reconcile one owned client/product/loan lifecycle through supported APIs; expand only after that succeeds. Activate only demo clients needed for loans, recording before/after status.

Proposed default: one clearly named synthetic demonstration product in an explicitly chosen demo currency (USD, not inferred from source files), simple fixed terms, no production accounting integration, and 30 loan applications across the cohort. This is lifecycle coverage, not a production lending configuration. Target 10 on-time, 10 late, six partial-payment and four approved-but-undisbursed scenarios. Derive schedule, paid/outstanding balances and observable state from API-returned schedules and actual supported commands. Do not directly assign statuses or fabricate source repayment history. Reconcile amounts using decimal arithmetic. Each scenario uses fixed dates no later than the local workbench business date, with documented observation cutoff and activation/application/approval/disbursement ordering.

Use a real native business record only if its supported API and required prerequisites can be verified. Otherwise put the business text in a clearly named fixture datatable and report that limitation. Likewise, use supported note/payment detail fields rather than weakening API validation or editing core ledger rows directly.

Count the pilot inside the 30 total applications, with one loan per selected client. At the fixed cutoff, use mutually exclusive acceptance definitions: ten disbursed loans with due installments paid and no overdue amount; ten disbursed loans with an overdue amount and no repayments; six disbursed loans with a positive repayment smaller than their due amount and a remaining overdue balance; four approved loans with zero disbursement. Use actual schedules to set supported dates and amounts. These scenario labels are fixture truth, not predictive labels for imported observations.

## Reproducibility and recovery

Keep the generated fixture, before-images, source crosswalk and ground-truth answer key in an ignored local runtime directory. Commit only generator/importer code, dependency pin, tests, schema and runbook, without source data or runtime secrets. A local manifest records payload hashes, generated identities, successful command results and entity IDs. Use stable owned external IDs; read and compare before creating/updating, and verify responses by reading stored records. A conflicting manual change stops that record for review. Never blindly retry an ambiguous financial POST; reconcile its recorded result/transaction ID before continuing.

Preflight checks target, tenant, existing provenance, expected original fixture, date configuration and disabled external integrations. Save a database backup and verify its exit status and nonzero size before applying the overlay. Preserve the matching private configuration. Do not reset the volume. Document fixture recovery from the private backup; identity-only rollback must not be advertised as reversing banking commands.

Before mutating the workbench, verify a restore of that backup in an isolated temporary database, compare schema and core/fixture counts, and leave the active tenant mapping untouched. A full working-instance restore requires stopping its application services, confirming the backup boundary and acknowledging that later unrelated changes would also be reverted. Never automatically restore over the active workbench after an importer error.

## Evaluation and acceptance

1. Original staging file/row hashes and observation datatables remain unchanged.
2. Exactly 100 existing clients receive the intended identity overlay; before-images and updated provenance reconcile.
3. Generated regional/global coverage, identifier classes, misplaced PII and clean controls reconcile with the manifest. Every claimed native occurrence is verified against stored values.
4. The successful pilot precedes the 30-loan batch. Product/application/schedule/transaction totals and scenario outcomes reconcile; unsupported paths are reported explicitly.
5. A repeat execution creates no duplicate clients, loans, notes or repayments and does not change generated identities.
6. Supply an evaluation harness/report contract that compares pipeline output against withheld ground truth. Report missed identifiers, false removals, repeated-identity linkage, allowed financial utility and malformed-record handling. An absent pipeline or policy is reported as 'not evaluated', never a privacy pass.
7. Test accidental leakage in extraction/export artifacts as well as primary records. Inspect full exported text for known planted values and distinguish exact matching from canonicalized variants. Ground truth and token/identity maps must not be included in analyst releases.

## Operator decisions proposed for review

Enrich the existing 100 shells; 80 regional/20 global profiles; 30 synthetic loans using a demo USD product; retain all imported observations; keep invalid or rejected stress cases outside typed core records; capture before-images and a backup; maintain a private evaluation answer key. These are proposed engineering defaults, not previously agreed client requirements.
