# Issue #39: operational compatibility preparation (2026-10-25 JST)

Formal execution remains **Terraform 1.14.9** with the six existing provider locks.
Adoption stays **HOLD**, Issue #39 stays **OPEN**, public release stays **NOT READY**.
This preparation adds executable evidence checks, not permission for AWS/State use.
See the [existing qualification inventory](P4_TOOLCHAIN_QUALIFICATION_20261025.md).

The official `latest` release endpoints were rechecked on this date and still resolve
to [Terraform 1.17.0](https://github.com/hashicorp/terraform/releases/tag/v1.17.0) and
[AWS Provider 6.70.0](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.70.0).
The preferred minimal-change candidate remains 1.16.7; no additional release change
was used to justify changing the formal pins.

## Provider State upgrader and default assessment

The recorded [official-source manifest](../backend/tests/fixtures/p4/aws-provider-source-review-20261025.json)
contains SHA256 digests of **46 files at each of 6.64.0, 6.65.0 and 6.70.0**:
41 used resource implementation files, four referenced State migration files,
and `go.mod`. Public files were read over HTTPS from the official repository;
no AWS credentials, State, saved Plan or historical private evidence was read.
This is source inspection, not execution of upstream Go migration tests.

Of the 41 primary files, **37 are byte-identical across all three versions**.
The four resource differences were reviewed:

| Resource / official candidate source | Observed change / adoption consequence |
| --- | --- |
| [SNS topic](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/sns/topic.go) | Adds optional/computed `maximum_message_size` and attribute mapping; no literal Default added. AWS readback may populate a new State value. Never infer unchanged State or adopt a guessed value from mock output. |
| [CloudWatch metric alarm](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/cloudwatch/metric_alarm.go) | Adds optional `evaluation_window`, conflict validation, API expand/flatten and State flattening. Existing literal defaults are unchanged in this file. Readback/default implications remain to be demonstrated. |
| [API Gateway v2 integration](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/apigatewayv2/integration.go) | 6.64.0 -> 6.65.0 adds identity/import metadata, shared importer and stricter empty-ID parsing. This is already in dev's provider baseline but new to test. Ordinary resource schema equality does not cover resource identity. Import/move remains forbidden during upgrade. |
| [IAM OIDC provider](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/iam/openid_connect_provider.go) | Extracts existing read flattening into a helper; no new permission/default in the reviewed file. This is not proof of effective IAM or generated helper behavior. |

The referenced [CloudWatch](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/cloudwatch/metric_alarm_migrate.go),
[DynamoDB](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/dynamodb/table_migrate.go),
[CloudFront](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/cloudfront/distribution_migrate.go)
and [S3 lifecycle v0](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/internal/service/s3/bucket_lifecycle_configuration_migrate_v0.go)
migration implementations are byte-identical across all three versions. Their
registration remains present in the resource files. Unchanged migration code does
not prove that real instance schema versions need no migration. Do not downgrade
or write State to experimentally establish that fact.

`go.mod` keeps plugin SDK v2 2.40.1, Framework 1.19.0 and plugin-go 0.31.0, but
changes Go, AWS SDK modules, terraform-json, plugin-log and transitive dependencies.
Shared helpers, generated identity registration and SDK behavior were not exhaustively
reviewed. The manifest scope deliberately excludes such a claim. Official
[State upgrade documentation](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade)
explains why schema versions and upgrader implementations must be assessed separately.

## Executable offline checks

`toolchain_migration.py --compare-provider-schemas` initializes two minimal,
backend-disabled roots from the existing official provider locks and compares
their schemas with 6.70.0 for all **41 used types**. These roots contain no resources,
data sources or repository backend. Source provider selection is checked before
initialization. Credentials/configuration isolation is inherited from the existing
runner. Only the two reviewed additions are allowed; missing types, changed schema
versions, unrelated schema changes, new providers or unsupported formats fail closed.
Both candidate Linux CI jobs now perform this comparison alongside the existing
six-scope lock/fmt/validate and 69 Terraform mocks. Normal required checks and pins
are unchanged. Schema reports explicitly say defaults/upgraders are **not proven**.

`toolchain_compatibility.py` compares supplied baseline/candidate **synthetic no-op
Plan JSON**. It executes no Terraform command. It traverses module resources and
rejects defaults/attribute/schema/address changes even when actions claim no-op,
IAM value changes, replacement/import/move, incomplete/errored/deferred/drifted
plans, unknown masks, failed/unknown checks and changed inputs/outputs. Empty resource
fixtures cannot pass as full operational evidence. Exact Terraform versions are
required; compatible JSON 1.x formats allow additive minor metadata according to
the [official JSON contract](https://developer.hashicorp.com/terraform/internals/json-format).
Only count/status is printed, never supplied resource values. This utility is not
connected to any production approval or Apply path.

```powershell
uv run --project backend --locked python -X utf8 backend/skills/p4/toolchain_migration.py `
  --repository . --temp-parent $env:TEMP `
  --terraform '<absolute checksum-verified candidate terraform.exe>' --candidate 1.16.7 `
  --compare-provider-schemas --export-directory '<new directory outside this repository>'

uv run --project backend --locked python backend/skills/p4/toolchain_compatibility.py `
  --baseline-json '<synthetic 1.14.9 JSON>' --candidate-json '<synthetic candidate JSON>' `
  --candidate 1.16.7
```

Repeat qualification for 1.17.0 only when its changed qualification needs checking.
Export is optional and never edits source: it verifies the qualification report's
source snapshot, exact six-scope migration and schema evidence before writing the
six candidate HCL files and six CLI-generated lockfiles to a **new** destination.
It rejects source drift, extra State files, unrelated HCL, altered locks, incomplete
evidence and existing destinations. `UPGRADE_HOLD.json` lists SHA256s and remaining
adoption gates. The twelve files alone are explicitly an **incomplete execution
migration**, not a merge-ready PR B. Never hand-edit provider hashes.

## Maintenance/recovery and PR B execution contract

| Consumer | Preserved contract / required PR B treatment |
| --- | --- |
| `bootstrap_state`, `maintenance_contract`, `bootstrap_maintenance` | Existing 1.14.9 State, binding, approval and saved Plan interpretation remains fixed. A future execution path must use a new operation/approval namespace and explicit candidate contract, not broaden the old version allowlist. |
| `recovery_contract`, `bootstrap_recovered_apply`, `recovery_migration` | Existing source/evidence/receipt integrity and consumed-operation guards remain unchanged. Restore or verify old evidence using its original source/toolchain. Do not reinterpret a prior receipt as candidate execution authority. |
| dev `terraform_dev`, cloud audit, test Closure | Existing shared new-execution constant remains 1.14.9. PR B must change all execution consumers and workflow pins together, binding fresh Plan/approval bytes to source, provider locks, exact CLI/platform, inputs and State identity. |
| JSON variables/null consumers | Real synthetic 1.14.9/1.16.7/1.17.0 boolean/null values are fed through the existing maintenance variable consumer. Historical State version rejection remains strict. This shape test does not authorize candidate maintenance execution. |

PR B preparation checklist (all items required before adoption):

1. Use the exported official two-platform locks and exact CLI/provider requirements
   across all six scopes. Choose 1.16.7 as preferred; keep 1.17.0 as comparator.
2. Update the shared future execution contract and every literal setup-terraform
   pin (`p4-standard-plan`, `p4-standard-apply`, `p4-cloud-plan`, `p4-compound`,
   `p4-deploy`, `p4-static`) atomically. Keep the existing Action commit pins.
   Update tests for the new execution contract while keeping historical pins/fixtures
   fixed. Do not weaken the normal additive lock guard or required checks.
3. Implement and independently review the future bootstrap execution namespace,
   preserving old readers and evidence. Candidate HCL must not make the original
   1.14.9 recovery executor run under a different version.
4. Extend synthetic resource/identity coverage and inspect remaining generated/shared
   provider paths. Any authorized real State/default/identity assessment needs a fresh
   separate account/environment/SHA/scope/cost/recovery approval; no such access has
   occurred here. Unexplained defaults, replacement or identity changes keep HOLD.
5. Never reuse a saved binary Plan or approval across toolchains. Produce fresh
   bindings/approvals with exact CLI/platform/locks/Plan/source hashes; unknown,
   partial, expired, consumed or mismatched evidence must stop before any mutation.
6. Obtain independent adoption/security review and genuine final-HEAD required CI.
   Explicitly release HOLD before merging a change that activates new formal pins.
   AWS Plan/Apply, readiness and deployment still require separate authorization.

No new Critical/High issue was found in this bounded preparation diff. The existing
High finding about the current runtime's CA fix remains unresolved until adoption;
source/schema/synthetic success does not remove it. AWS effective IAM, real State,
replacement/default drift and full future maintenance execution remain unproven.

## Local verification recorded for this preparation

- Related Python compatibility/migration/maintenance/recovery tests: **310 passed,
  1 skipped**. After final validation hardening, the changed compatibility/migration
  and pin tests: **102 passed**. Ruff check/format and `git diff --check` pass.
- Native Windows **1.16.7**: official SHA256SUMS-verified archive; fresh credential-free
  six-scope lock/fmt/backend-disabled init/validate; **10/57/2** existing Terraform
  mocks pass. Both baseline provider schemas compare successfully for all 41 types.
  The final schema checker was also run against those captured native JSON outputs.
- A real candidate export produced **12** HCL/official lock files plus HOLD manifest
  outside the source checkout. The active six Terraform requirements/locks and
  historical maintenance/recovery files have no changes in this preparation.
- Genuine final-HEAD Linux/required Actions must be recorded on the PR. No assertion
  here treats the previous PR's successful CI as validation of this new change.
- Local results are offline evidence only. No AWS authentication/API/read, remote
  State, formal Plan/Apply, IAM/resource change, readiness change, deployment or
  paid inference was executed.
