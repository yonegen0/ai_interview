# Security review and dependency audit — 2026-10-25 JST

## Scope and evidence

Reviewed main `2f7c3cffb4571f0dcafa0ab75378d5f1d8b68e8e`, after ordinary merge of
[PR #36](https://github.com/yonegen0/ai_interview/pull/36). Its base was
`8ca7b6054b21fcb85648ec42915c89000eb4015e`, head
`cc7c4de22ae54234f54934e992fc42c6ee9e8114`. The two changed files were reviewed
individually: backend checkout credential persistence, and frontend permissions,
checkout, and audit sequencing. No blocking defect or source/lockfile change.
PR review counts: Critical 0 / High 0 / Medium 0 / Low 0. External advisory
availability, duplicate audit requests, and production audit skipping after a
failed all-dependency audit remain operational limitations of the existing PR CI.

GitHub Actions PR runs, latest attempt 1, all completed successfully on that head:

| Workflow | Run | Required job results |
| --- | --- | --- |
| Backend | 40120898765 | Backend verify SUCCESS |
| Frontend | 40120898744 | Frontend verify SUCCESS, including both audits and E2E |
| Offline infrastructure/package | 40120898750 | terraform/package_changes SUCCESS; package SKIPPED |

`package_changes.py` reported unchanged package inputs. The two workflow changes
are outside its build input set. The conditional package skip was accepted by
GitHub: ruleset `main-pr-and-ci` (24886774) was active, strict, with all five checks,
review-thread resolution, no bypass actors, deletion/force-push protection, and
zero required approving reviews. No reviews or unresolved review threads existed.
The fresh review in this task was an agent review; it is not a GitHub approving
review or independent human approval. Ready transition and merge used the expected
head SHA, without branch deletion or protection changes.

Post-merge main runs also completed successfully, all at attempt 1 and exactly
`2f7c3cffb4571f0dcafa0ab75378d5f1d8b68e8e`: Backend 40121756345,
Frontend 40121756243, and offline infrastructure/package 40121756392. The required
five jobs again ended in four SUCCESS results and the expected package SKIPPED;
both npm audits and Playwright E2E succeeded. The merged two files match the
reviewed PR head exactly.

## Local dependency verification

Used an isolated clean source checkout of the audited main, preserving the user's
original dirty checkout. Local Node was 24.22.1/npm 11.19.1; the adopted CI Node is
22.23.4, so local npm results are supplementary rather than equivalent CI evidence.

- `npm audit --package-lock-only --include=dev --audit-level=low --json`: exit 0,
  all severity counts 0.
- `npm audit --package-lock-only --omit=dev --audit-level=low --json`: exit 0,
  all severity counts 0.
- uv 0.13.5, CPython 3.14.9: `uv lock --check` and `uv sync --locked`: PASS.
- Hashed `uv export --locked --no-emit-project` output audited with pip-audit
  2.10.1, `--strict --no-deps --disable-pip --require-hashes`: exit 0,
  no known vulnerabilities. Runtime and default development dependencies included.
- `uv run --locked pytest -q tests/unit/test_ca_bundle.py` from backend: 1 passed.
  TLS certificate verification remains required; the test checks the botocore
  bundle excludes AAA Certificate Services and emSign ECC Root CA - G3.
- No dependency or lockfile modification. No separate Linux container or local
  Mock/E2E rerun; Linux verification is provided by genuine GitHub Actions.

The Python lock includes boto3/botocore 1.43.118, urllib3 2.8.0, Pydantic 2.13.5,
and pydantic-core 2.46.5. No known package advisory was reported by this audit at
execution time. Python 3.14.9's [official security release notes](https://www.python.org/downloads/release/python-3149/)
describe updated bundled pip/certifi for the eMudhra incident. Package audits do
not establish complete runtime, operating-system, or application security.

## GitHub Actions static audit

Reviewed all 12 existing workflows: 41 external-action references use full commit
SHAs; all 15 checkouts disable credential persistence; all workflows default to
`contents: read`. No `pull_request_target`, `workflow_run`, `secrets: inherit`,
`continue-on-error`, or direct expression interpolation in shell bodies was found.
AWS/OIDC workflows are manual and guarded by main/ref/attempt/approval checks.
Environment branch policies are main-only. No Environment setting was changed.

Reviewed bounded frontend failure artifacts, encrypted plan-journal publishing,
approval identity guards, and lockfile-keyed package cache use. Public advisory
queries for the five Action repositories and the Actions advisory ecosystem found
no applicable advisory. This does not cover every transitive dependency embedded
inside an Action or all historical logs/artifacts. No reproducible Critical,
High, Medium, or Low Actions defect was identified within this scope.

References: [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use),
[cache access restrictions](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

## Application static audit: one Medium finding

Critical 0 / High 0 / Medium 1 / Low 0 in the reviewed source paths.

**Session creation lacks a per-user creation budget.** An authenticated user can
repeat `POST /sessions` using fresh idempotency keys. `repositories/domain.py`
`create_once` creates Session and IdempotencyRecord entries without a per-owner
time-window limit. Session has no expiry; the codec's STAR expiry handling does
not apply to Session. The declared API stage throttle (20 requests/sec, burst 30)
is shared and best effort, rather than a per-user storage or cost limit.

Risk: continued storage/API work and shared rate exhaustion without calling AI.
The administrator-invited, maximum-30-user assumption limits exposure, but this
remains a public-release concern. Proposed independent change: an atomic per-owner
Session creation budget, preserving idempotent replay without charging it again.
Do not add TTL to retained Session data or alter API/recovery contracts implicitly.
[AWS throttle limitations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html).

Other reviewed defenses: Email OTP/admin invitation, declared JWT authorizer
issuer/audience plus runtime claim/source checks, ADMIN authorization, owner-keyed
records, input/AI output schemas, asynchronous lease/idempotency guards, identity
cache clearing, and bounded logging without response/token bodies. These are code
observations, not AWS effective-setting or live attack-test results.

## Lightweight recurring verification

`dependency-audit.yml` runs weekly Monday 06:23 JST (Sunday 21:23 UTC), and on
relevant PR/main dependency/workflow changes. The npm all/production matrix runs
independently with fail-fast disabled; a failed all-dependency scan does not cancel
production evidence. Lockfile-only audits execute no project install scripts.
Python exports the locked runtime/default development requirements and audits exact
hashed versions with strict collection errors. No ignored advisory, auto-fix,
error-to-success conversion, E2E, artifact upload, AWS credential, or OIDC grant.
All actions are SHA-pinned; each of the three jobs has a 10-minute timeout.

This adds three short jobs weekly, rather than running the complete test/build/E2E
suite on a timer. Public advisory outages remain failures. GitHub schedules can be
delayed or disabled by repository inactivity; Actions notifications depend on user
settings. Existing five required checks and ruleset are unchanged. Future optional
extras/non-default Python dependency groups need an explicit coverage decision;
platform markers are evaluated on the Linux audit runner.

References: [npm audit](https://docs.npmjs.com/cli/v10/commands/npm-audit/),
[uv export](https://docs.astral.sh/uv/concepts/projects/export/),
[pip-audit](https://github.com/pypa/pip-audit),
[GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Terraform update preparation: HOLD pending compatibility checks

All six roots/modules require Terraform `= 1.14.9` and AWS Provider `~> 6.0`.

| Root/module | Committed AWS lock |
| --- | --- |
| bootstrap | 6.64.0 |
| environments/dev | 6.65.0 |
| environments/test | 6.64.0 |
| environments/web | 6.65.0 |
| modules/frontend | 6.65.0 |
| modules/service | 6.64.0 |

Official candidates at review time: Terraform
[1.17.0](https://github.com/hashicorp/terraform/releases/tag/v1.17.0), alternative
[1.16.7](https://github.com/hashicorp/terraform/releases/tag/v1.16.7), and AWS Provider
[6.70.0](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.70.0).
These release notes describe Go 1.26.10/eMudhra CA security changes. The old source
tags declare Go 1.25.8 (Terraform 1.14.9) and 1.26.6 (Provider 6.65.0); do not assume
the current toolchain includes the newer trust changes. This is an outstanding
toolchain advisory/compatibility concern, not proof of an actual compromise.

The runtime guards, recovery/maintenance contracts, fixtures, and six CI workflows
strictly pin old versions; the Runbook explicitly preserves the adopted recovery
toolchain. A global string replacement would break historical evidence validation.
Terraform 1.17 version JSON and local plan-show changes also need compatibility
tests. Provider 6.68/6.70 breaking notes concern resource types absent from current
HCL, but that alone does not establish full compatibility.

Prepare an independent version-update branch/PR: fix candidate versions, distinguish
new execution contracts from historical evidence validation, formally generate all
six locks in a backend-disabled credential-free copy, validate/mock each root,
exercise IAM non-expansion negative tests and synthetic Plan JSON audit fixtures.
Keep update merge on hold until those checks pass. No Terraform init, formal
Plan/Apply, State read/change, or AWS authentication/connection was executed here.

## Release status

**NOT READY for public release.** Outstanding: the Medium Session budget finding,
toolchain compatibility/security update, final security review, separately approved
Stage2 Plan/Apply, real Bedrock verification, STAR integration verification, live
AWS E2E/security validation, and fresh performance measurement. No AWS success or
actual AI success is inferred from source, mocks, package audits, or CI.
