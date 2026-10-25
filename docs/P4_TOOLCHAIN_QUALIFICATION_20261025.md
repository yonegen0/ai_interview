# Issue #39: offline toolchain qualification (2026-10-25 JST)

This prepares a migration; it does **not** adopt a new runtime. Formal execution
remains Terraform 1.14.9 with existing provider locks. Issue #39 stays open and
public release remains **NOT READY**. Offline success is not AWS/State/IAM proof.

## Official release assessment

Official `latest` links resolved to Terraform **1.17.0** and AWS Provider
**6.70.0** on October 25. Both candidate CLIs and this provider identify Go
**1.26.10**, containing the `crypto/x509` eMudhra intermediate CA distrust fix
(CVE-2026-111943). Security qualification and operational compatibility are separate.

| Candidate / official source | Assessment |
| --- | --- |
| [CLI 1.16.7](https://github.com/hashicorp/terraform/releases/tag/v1.16.7) | Go 1.26.10; test-schema panic fix. Preferred adoption comparator, not yet selected for execution |
| [CLI 1.17.0](https://github.com/hashicorp/terraform/releases/tag/v1.17.0) | Same cited trust fix; version JSON adds `format_version`; local-plan show variable behavior changes; additional provider/planning features |
| [AWS 6.70.0](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.70.0) | Go 1.26.10; Route53 Domains delegation signer import ID changes. Exactly pinned in disposable copies only |

[Go history](https://go.dev/doc/devel/release) records 1.26.10 on October 19.
Candidate Windows binaries also contain `go1.26.10` build strings. This inspection
supplements checksum verification; no claim covers every possible vulnerability.

1.14.9 -> 1.16.7 crosses minor releases:
[1.15](https://github.com/hashicorp/terraform/releases/tag/v1.15.0) changes S3
FIPS/dualstack environment switches to interpret only true/false, and changes
provider installation messages/order;
[1.16](https://github.com/hashicorp/terraform/releases/tag/v1.16.0) corrects
provisioner `bastion_host_key` behavior. No provisioner is declared here; real S3
execution remains untested. Neither candidate is merely a 1.14 patch.

Provider releases
[6.65](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.65.0),
[6.66](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.66.0),
[6.67](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.67.0),
[6.68](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.68.0),
[6.69](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.69.0)
were also inspected. SNS topic maximum message size and CloudWatch alarm evaluation
windows are notable used-resource additions. DocumentDB/RDS availability-zone count
validation (6.68) and the 6.70 Route53 Domains import change target types not
declared here. This is not proof of no changed defaults, replacement or State migration.

Actual credential-free `providers schema -json` comparison covered all **41 used
resource types**, with **no declared data sources**, for 6.64.0/6.65.0 -> 6.70.0.
Only SNS topic (`maximum_message_size`, optional/computed number) and CloudWatch
metric alarm (added `evaluation_window` block) differed; their schema versions
stayed 0 and 1. Other used type schemas were equal. No used type or existing
attribute/block was removed. This does not inspect State upgrader code or prove
no replacement/default/IAM changes.

## Inventory / preserved contracts

| Scope | CLI definition | Existing CLI | AWS lock | Local module dependency |
| --- | --- | --- | --- | --- |
| bootstrap | main.tf | = 1.14.9 | 6.64.0 | none |
| environments/dev | main.tf | = 1.14.9 | 6.65.0 | ../../modules/service |
| environments/test | main.tf | = 1.14.9 | 6.64.0 | ../../modules/service |
| environments/web | main.tf | = 1.14.9 | 6.65.0 | ../../modules/frontend |
| modules/frontend | main.tf | = 1.14.9 | 6.65.0 | none |
| modules/service | versions.tf | = 1.14.9 | 6.64.0 | none |

All existing requirements use `~> 6.0` and lock AWS only. Qualification copies use
`= 6.70.0` (canonical lock constraint `6.70.0`). No tracked HCL/lock is upgraded.
Each generated lock must contain two platform `h1` entries and official archive
`zh` checksums, and all six must agree structurally. Hash counts alone do not
authenticate provenance; the runner obtains locks from the official registry CLI.

- `cloud_toolchain.NEW_EXECUTION_TERRAFORM_VERSION` explicitly names the future
  execution setting; it remains 1.14.9, with the old constant as a compatible alias.
- `terraform_dev.py`, `cloud_controller_core.py`, `test_closure_apply.py` and all
  their version checks now consume that new-execution constant, whose value remains
  1.14.9. Candidate binaries fail the pre-OIDC gate. Historical pins do not import it.
- Setup pins remain 1.14.9 in standard Plan/Apply, cloud-plan, compound, deploy,
  and static workflows. The new qualification workflow has no deployment permission.
- Historical `bootstrap_state.py`, `maintenance_contract.py`, `recovery_contract.py`,
  `bootstrap_recovered_apply.py`, the 1.14.9 maintenance fixture and approved evidence
  retain their original independent contracts. No historical authorization migrates.

`terraform_dev.assert_binding` still requires exact binding equality and matching
plan bytes. Added negative tests exercise Terraform version, lock SHA256, source SHA,
plan SHA and altered binary bytes. Expiry, UNKNOWN/partial results, State and IAM
guards remain in the existing Backend suite. These are synthetic/Fake tests.

## Reproduction and evidence boundaries

`backend/skills/p4/toolchain_migration.py` is opt-in. Normal
`offline_terraform.assert_additive` and baseline CI are unchanged. Supply a verified
absolute CLI path. The runner snapshots source, copies the normal offline allowlist
into a fresh directory, excludes tfvars/State/backend input/old metadata, strips
AWS/TF environment, disables metadata and uses empty AWS configuration/credentials.
Only six literal CLI/provider declarations may change. Extra providers, partial
migrations, unrelated IAM/backend/HCL changes and inconsistent locks fail closed.

The official CLI regenerates six locks using
`providers lock -platform=linux_amd64 -platform=windows_amd64`. Checks run **before**
`init -backend=false -input=false -lockfile=readonly`. All six scopes receive fmt
and validate; the three existing module/bootstrap mock suites run. No formal
plan/apply/show/state commands exist in this runner. Original source is rechecked
on success/failure; success reports are written only after that final check.
Fresh work directories/logs are retained and no private evidence is overwritten.

```powershell
uv run --project backend --locked python backend/skills/p4/toolchain_migration.py `
  --repository . --temp-parent $env:TEMP `
  --terraform '<absolute verified candidate terraform.exe path>' --candidate 1.16.7
```

Repeat for 1.17.0. The new Actions workflow runs both on Linux with `contents: read`,
no environment, OIDC, deployment dispatch or private artifact upload. It does not
change required checks or protection. Genuine results must match the current HEAD.
See official [provider lock](https://developer.hashicorp.com/terraform/cli/commands/providers/lock),
[dependency locks](https://developer.hashicorp.com/terraform/language/files/dependency-lock),
and [automation guidance](https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform).
Saved Plans require matching CLI/provider toolchains, architecture and relevant paths.

The Windows system CLI is 1.14.9, Node 24.22.1, uv 0.13.5; `python` is a Store
alias, so locked uv selected CPython 3.14.9. Linux is WSL Ubuntu 24.04 x86_64.
Candidate binaries coexist at separate paths. Downloads used normal TLS and official
SHA256SUMS at `https://releases.hashicorp.com/terraform/<version>/`. Detached CLI
archive signature verification is not claimed.

| Official CLI archive | Verified SHA256 |
| --- | --- |
| 1.16.7 windows_amd64 | b22dfa64a9530c9b7774f840d98e9bfadc1ae33b1bd2083ffa976828c46e542c |
| 1.17.0 windows_amd64 | 2948dd7f77dec0f562ec29000103e0441d915be5e5f1a02c1ce23681951cfb19 |
| 1.14.9 linux_amd64 | 2e5cffc20a0b48a67a76268723bd5a10b8666f69b2aa4f04906e206726bedd63 |
| 1.16.7 linux_amd64 | 5454efcf7fc87f0c2113111b9a5c7182f0ca1c6f0f23a1e110a50770a8fe473b |
| 1.17.0 linux_amd64 | c168cab7c637a8769fdb90089ddd19de701bc6ff8aca64dc2e2185fe46f59f67 |

Three new `terraform-<version>-offline-json.json` fixtures contain actual Windows
`version -json` / `show -json` from **synthetic output-only local Plans**, with no
provider, remote backend, repository resources or production State. The old
maintenance fixture is unchanged. All three show format 1.2, boolean false and
dynamic null output; version format 1.0 appears in 1.17.0. All six cross-version
synthetic-plan show attempts failed. No Apply was attempted. This does not prove
full AWS plan compatibility.

Windows 1.16.7 and 1.17.0 both completed six-scope lock generation, fmt, backend-free
init/validate and mock tests: bootstrap **10**, service **57**, frontend **2** passed
per candidate. Linux qualification and genuine CI are recorded in the PR;
incomplete/missing reports never imply success. Local targeted Backend tests passed
**277** cases (2 skipped), including **45** new migration/JSON/binding cases; Ruff check/format pass.
The first full Windows run reported 2313 passed, 40 failed, 9 errors, 4 skipped and
57 deselected. Windows diagnostic ACL refusal was reproduced on unchanged main
84f390c, and OpenSSL was absent from PATH; these are not a passing full-suite claim.
The existing Git OpenSSL executable is used for a separate encryption recheck;
Linux current-HEAD CI remains mandatory. No ACL guard is relaxed to make tests pass.

## Bounded security review / remaining HOLD

| Severity | Disposition |
| --- | --- |
| Critical | No new finding in this bounded preparation review; not a full-system audit |
| High | Current runtime has not adopted the cited CA fix; unresolved pending qualified upgrade. Exposure/exploitability not established |
| High | Cross-version Saved Plan execution stays forbidden; original guards retained, negative coverage added |
| Medium | Real-State upgrades, defaults/replacement/drift and effective IAM remain unverified |
| Low | Explicit fixture/source provenance improves reproducibility; offline success still grants no execution authority |

Adoption stays Draft/HOLD until the six-scope Windows/Linux matrix, State upgrader
review, bootstrap maintenance/recovery future execution design,
Plan/Apply pins and exact locks, full operational JSON consumers, expiry/hash/source/
platform/UNKNOWN/IAM/State negative tests, independent review and genuine CI pass.

No AWS login/read, remote State, formal Plan/Apply, IAM/resource change, readiness
change, deployment or paid inference is authorized here. Stage2, real DynamoDB
quota concurrency, Bedrock inference, STAR deployment, Cognito/Recovery E2E and
p95/30-evaluation measurement need fresh separate execution approval. Historical
p95 2003.466 ms is a past FAIL, not a new measurement.
