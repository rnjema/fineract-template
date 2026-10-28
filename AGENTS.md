# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

This repository is a **fork of Apache Fineract 1.8** ("branched off fineract-V1.8.0", see the
README) that has been customized for a specific deployment (remote: `rnjema/fineract-template`,
CI workflows named `inkomoko*`, MySQL credentials and Liquibase changesets referencing
Inkomoko/CGLT tickets). It is a **core banking / microfinance platform** exposing a REST API for
clients, loans, savings, accounting, and reporting.

The upstream project is Apache-licensed; this fork adds local modifications (extra dependencies
such as JasperReports, MinIO, ICU4J, PDFBox in `fineract-provider/build.gradle`, extra REST
endpoints under `portfolio` and `infrastructure`, and one-off data-correction SQL under
`docs/ops/`). When editing, respect both upstream Fineract conventions and the fork's local
changes — do not "clean up" fork-specific code as if it were upstream.

Main documentation is `README.md` (Apache Fineract). This file summarizes what an agent needs.

## Technology stack

- **Java 17** (source/target compatibility set in root `build.gradle`), Gradle wrapper **7.5**
  (`gradle/wrapper/gradle-wrapper.properties`).
- **Spring Boot 2.7.1** monolith; entry point `org.apache.fineract.ServerApplication`
  (`fineract-provider/src/main/java/org/apache/fineract/ServerApplication.java`).
- **JPA via EclipseLink** with static weaving of entity classes at compile time
  (`compileJava.doLast` in `fineract-provider/build.gradle`) — this is why a plain IDE build
  can behave differently from the Gradle build.
- **Databases**: MariaDB/MySQL by default (the fork's `docker-compose-local.yml` uses
  MySQL 5.7), PostgreSQL also supported. Schema migrations via **Liquibase** changesets in
  `fineract-provider/src/main/resources/db/changelog/`. Multi-tenancy: a `fineract_tenants`
  database plus one schema per tenant (e.g. `fineract_default`).
- **API**: Jersey (JAX-RS) resources, Spring Security with mutually exclusive HTTP Basic /
  OAuth2 schemes plus optional two-factor auth. OpenAPI/Swagger docs generated during build
  (`resolve` task) from `fineract-provider/config/swagger/fineract-input.yaml.template`.
- **Other**: Pentaho + JasperReports reporting, optional ActiveMQ/Kafka
  messaging (`activeMqEnabled` Spring profile), Signoz/OpenTelemetry observability
  (`docker-compose.signoz*.yml`, `signoz/`, `scripts/signoz-*.sh`), Jib for container images.

## Repository layout (Gradle multi-module, see `settings.gradle`)

| Module | Purpose |
| --- | --- |
| `fineract-provider` | The main application — ~all business logic. |
| `fineract-war` | Traditional WAR packaging for external Tomcat 9 (JAR deployment preferred). |
| `fineract-client` | Java client generated from the OpenAPI spec (`org.openapi.generator` plugin). |
| `fineract-doc` | Asciidoctor documentation. |
| `integration-tests` | JUnit 5 + Cucumber integration tests; spins up Tomcat via Cargo for some suites. |
| `twofactor-tests`, `oauth2-tests` | Integration tests for the 2FA / OAuth2 security profiles. |
| `instancemode-tests` | Tests for the Batch API under the instance-mode filter (read-only vs. read-write node). |
| `karate-tests` | Karate DSL API tests. |
| `module/dummy` (`core`/`service`/`starter`) | Template showing how to build a custom add-on module. |
| `custom/foo` | Example of a downstream customization module (`com.acmecorp...`). |

Inside `fineract-provider/src/main/java/org/apache/fineract/` the code is split into:

- `portfolio/` — domain features: `loanaccount`, `savings`, `client`, `group`, `accounting`,
  `charge`, `collateralmanagement`, `repaymentwithpostdatedchecks`, `supplier`, etc.
- `infrastructure/` — cross-cutting platform code: `security`, `jobs`, `codes`, `hooks`,
  `documentmanagement`, `dataqueries`, `businessdate`, `instancemode`, `Odoo`, `africastalking`, ...
- `commands/` — command/audit infrastructure; `cob/` — close-of-business processing;
  `notification/`, `batch/`, `template/`, `mix/`, `adhocquery/`, `interoperation/`,
  `useradministration/`, `organisation/`, `scheduledjobs/`, `spm/`.

## Build and run

Requires Java 17 and a MySQL/MariaDB server on `localhost:3306`.

```bash
./gradlew createDB -PdbName=fineract_tenants
./gradlew createDB -PdbName=fineract_default
./gradlew bootRun                       # run the app (dev)
./gradlew clean bootJar                 # self-contained JAR in fineract-provider/build/libs
./gradlew :fineract-provider:jibDockerBuild -x test   # Docker image, then `docker-compose up -d`
```

Notes specific to this fork:

- Database helper tasks have fork-specific defaults; inspect and override these through
  reviewed private local configuration. Do not copy credentials into documentation.
  There are also PostgreSQL/MySQL variants and a password-reset helper; do not run these
  against an existing workbench as a connection workaround.
- `docker-compose-local.yml` is the fork's local-dev stack (MySQL 5.7 + fineract on port 8080);
  the upstream `docker-compose.yml` uses MariaDB and HTTPS on 8443.
- The app must run with the JVM timezone **UTC** (dates are stored in UTC; see README
  "IMPORTANT: if you use MySQL or MariaDB"). The Docker image already sets `-Duser.timezone=UTC`.
- JDBC drivers are deliberately excluded from the published artifacts for licensing; the
  `bootRun`, `jib` and test configurations add MariaDB/PostgreSQL/MySQL drivers back in.

## Testing

```bash
./gradlew clean test          # needs the fineract_tenants + fineract_default databases created first
./gradlew clean build jacocoTestReport   # coverage report under build/code-coverage
```

- Tests are JUnit 5 (`useJUnitPlatform()`), with Cucumber and Retrofit-based test clients.
  Integration tests live in `integration-tests/src/test/java/org/apache/fineract/integrationtests/`
  (e.g. `ClientLoanIntegrationTest`, `AccountingScenarioIntegrationTest`).
- `fineract-provider` unit tests live in `fineract-provider/src/test/java/...`.
  `ClasspathHellDuplicatesCheckRuleTest` fails when dependency changes introduce duplicate
  classes across JARs — if you bump versions, run `./gradlew dependencies` and add `exclude`s
  in the relevant `dependencies.gradle`.
- Some integration suites download and run an embedded Tomcat via the Cargo plugin and can be
  slow/flaky; the upstream README documents the procedure for handling flaky tests
  (`@Disabled // TODO FINERACT-xxx`, tracked in JIRA).
- `bootRun` integration tests under `core/boot/tests/**` are excluded unless you pass
  `-Penv=dev`.

## Code style and conventions

Enforced by the build (violations fail the build):

- **Spotless** with `config/fineractdev-formatter.xml` (Eclipse formatter profile) — run
  `./gradlew spotlessApply` before committing; `./gradlew spotlessCheck` to verify.
- **Checkstyle** (`config/checkstyle/checkstyle.xml`), **SpotBugs**, **Modernizer**,
  **Error Prone**, and **Apache RAT** (license header check — every source file needs the ASF
  license header; run `./gradlew rat`).
- Dependencies: never use `compile`/`api` scope; use `implementation`, `runtimeOnly` or
  test scopes (see the comment at the top of `fineract-provider/dependencies.gradle`).
- Logging: SLF4J only — never `System.out`/`printStackTrace()`; use parameterized messages
  (`LOG.error("... {}", x, e)`); `LOG.trace()` is not used. See README "Logging Guidelines".
- Error handling: never swallow exceptions; always include the root cause; never catch
  `NullPointerException`; in tests propagate exceptions or use `assertThrows`. See README
  "Error Handling Guidelines".
- Commit messages: imperative mood, concise, referencing a JIRA/FINERACT issue (or fork ticket
  like CGLT-xxx) in parentheses, e.g. `Fix inability to reschedule loan (FINERACT-1109)`.
- All human-facing documentation and comments are in **English**.

## Security considerations

- Default demo credentials are `mifos` / `password` — never expose an instance with these.
- Basic auth and OAuth2 are mutually exclusive; startup fails if both are enabled
  (`FINERACT_SECURITY_BASICAUTH_ENABLED` / `FINERACT_SECURITY_OAUTH_ENABLED`,
  optional `FINERACT_SECURITY_2FA_ENABLED`).
- Do not commit real secrets: the repo contains example/placeholder env files only
  (`.env.signoz.example`). Note the DB passwords in `fineract-provider/build.gradle` and
  `docker-compose-local.yml` are fork-internal development values — keep them consistent
  rather than "fixing" them silently.
- `docs/ops/CGLT-592-phantom-redraw-impact.sql` and `CGLT-624-residual-penalty-impact.sql` are
  **read-only production data-correction assessment scripts** (phantom loan-redraw bug). Treat
  them as documentation of past incidents; do not run them against a database, and do not
  delete them — they explain fork-specific behavior in the loan repayment/redraw code.

## CI / deployment

- GitHub Actions under `.github/workflows/`: `inkomoko*.yaml` build the `bootJar` on JDK 17 and
  publish Docker images per environment (staging/uat/production); `spotless.yml` runs Spotless
  checks; `sonarqube.yml` runs SonarQube analysis; `jira-commit-check.yml` validates commit
  messages; `stale.yml` is the standard stale-PR bot.
- Kubernetes manifests in `kubernetes/` (fineract-server + MySQL deployments,
  `kubectl-startup.sh` / `kubectl-shutdown.sh`); Helm `Chart.yaml` at repo root.
- Versioning uses the `jgitver` Gradle plugin (git-tag/SHA based), no hardcoded version.
