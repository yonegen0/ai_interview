# Issue #50 offline follow-up and remaining production gates

Baseline: main `b276568908d7c96c41c083d5bcbcc64d955945f6`, 2026-10-25 JST.
Issue #39 is CLOSED; #50 remains OPEN. PR #51/#52 are merged and preserved.
Formal Terraform remains **1.14.9**. PR #43 remains **Draft/HOLD**, no auto-merge.
This report grants no execution, enrollment, State, IAM, deployment or adoption rights.

## Concrete changes and independent review

An independent read-only reviewer reproduced a P2 in
`candidate_toolchain_probe.py`: replacing a checked regular binary or LICENSE
with a FIFO before `read_bytes()` could block Python indefinitely, before the
Terraform subprocess timeout. Two regression cases failed before the repair
with five-second subprocess timeouts. Descriptor reads now use
`O_NOFOLLOW | O_NONBLOCK`, reject nonregular files with `fstat`, compare descriptor
and pathname identities before/after reading, and always close the descriptor.
The same helper protects CLI, Provider and LICENSE bytes. This narrows races;
it does not establish protected filesystem ownership or immutable execution.

The reviewer independently ran the ten probe tests under WSL, empty environment
and `unshare -n`: **10 passed**. No other reproduced P0/P1/P2 was found in the
reviewed snapshot, producer receipt, evidence gate and SQLite paths. This is a
separate agent's source review on the same host, not independent operational trust.
The two ChatGPT-owned signature files were not edited; producer verification
inherits PR #52's issuance/key-validity check.

Two additional SQLite regressions demonstrate explicit limits, rather than add
an authority: rolling back DB and caller checkpoint together permits local
re-reservation, and separate DBs permit the same IDs. All results retain
`authorized=False`, `retry_permitted=False`, and unproven global/rollback flags.

PR #43 was merged with the baseline by ordinary merge `31a8408`, without rebase
or force push. Its subsequent commit `e72d4e8` contains the probe repair plus
held-branch integration fixes. Its immutable migration baseline moves from
`7ec3595` to the full baseline SHA above: the only intervening Terraform inventory
addition was `terraform/AGENTS.md`. The exact six HCL/six generated-lock comparison
is retained. Two stale tests now explicitly distinguish legacy maintenance
1.14.9 from PR #43's held new-execution proposal 1.16.7. Those branch-specific
workflow/pin-test changes are excluded from this independent offline repair.

## Actual CLI and Provider observations

Archives were checked against freshly retrieved official HTTPS SHA256SUMS;
cached archives were rehashed and extracted into a new private work directory.
Official PGP signer trust was **not authenticated**. Hash agreement alone is not
signer enrollment, revocation freshness or execution attestation.

| linux_amd64 product | ZIP SHA256 | Executable SHA256 |
| --- | --- | --- |
| Terraform 1.16.7 | `5454efcf7fc87f0c2113111b9a5c7182f0ca1c6f0f23a1e110a50770a8fe473b` | `54533008a91f4aa992bb530963f6a902f67f4cf75245c014cdf57df4afb8d2ec` |
| Terraform 1.17.0 | `c168cab7c637a8769fdb90089ddd19de701bc6ff8aca64dc2e2185fe46f59f67` | `664b66cc0bcd7ed28fd27569719ccaa8a40c230b8be45060ce4d65e2852e1bcc` |
| AWS Provider 6.70.0 | `58acc041b080778ded75320e241ebcf6cf2ed145bede644b86a4784ce46086c6` | `75d70f99d54bbef98e8f200ff0df71d2147e309cf46269a21eabf9c3842f7183` |

Provider package inventory SHA256 (executable plus LICENSE, sorted JSON):
`27f68be7b1584292b4339708a5546bc7217bbc434dc780a71016b04a06361728`.
The existing `candidate_toolchain_probe.probe` was reused for both real CLIs;
version/platform, readonly lock agreement, inventory, init/validate/schema and
post-use binary checks succeeded. No replacement repository probe was added.

| Disposable scope from PR #43 | 1.16.7 | 1.17.0 | Mock tests per CLI |
| --- | --- | --- | --- |
| bootstrap | init/validate PASS | init/validate PASS | 10 PASS |
| environments/dev | init/validate PASS | init/validate PASS | existing suite has no root Mock run |
| environments/test | init/validate PASS | init/validate PASS | existing suite has no root Mock run |
| environments/web | init/validate PASS | init/validate PASS | existing suite has no root Mock run |
| modules/service | init/validate PASS | init/validate PASS | 57 PASS |
| modules/frontend | init/validate PASS | init/validate PASS | 2 PASS |

All these commands ran with `env -i`, a new empty HOME, no credential files,
fixed CLI config, filesystem mirror only, and a separate Linux network namespace
containing only loopback. Public archive downloads happened separately before
isolation. `init` used `-backend=false -input=false -lockfile=readonly`; original
tracked source/locks and copied locks were rechecked. There were **69 Mock tests
per CLI**, not 69 in every scope. Provider schemas were compared with independently
initialized 6.64.0 and 6.65.0 mirrors using the existing `compare_schemas`.
Computed/default/State-upgrader compatibility remains unproven.

Native Windows `version -json` succeeded for both newly extracted CLIs in sterile
directories and allowlisted environments. Executable SHA256:
1.16.7 `ce3ba132f14197fb5a9de79696f86603439e0801592d066a9e6624272d20a63d`;
1.17.0 `ea648bfb3d3db4a331e66ecb4cddeb2c5c250e9dc3886fc49ba136de56fefa68`.
This establishes Windows CLI version observation only. The protected probe is
Linux-only and fails closed without its namespace/no-follow prerequisites;
Windows Provider execution and full native Windows regression were not performed.

## Real local Plan boundary

A disposable local Git repository with the required source inventory and only
built-in `terraform_data` in its executed root produced an actual saved Plan
under Terraform 1.16.7. There was no AWS Provider in this Plan, AWS resource,
credential, remote backend, State readback or Apply. Backend-disabled init,
`plan -refresh=false -lock=false -input=false -out=...` and `show -json` succeeded
inside the isolated namespace. The process return status was checked before
snapshotting; the original Plan was preserved privately before substitution.

The generated Plan was **1,534 bytes**, SHA256
`d554430a95eb9208674b8f3c156fd481cca7e5dd5247a72ede76cff41037c34f`.
The existing bounded Plan reader matched those exact bytes, Terraform `show`
identified only `terraform_data`, and source snapshots matched before/after.
Later Plan and tracked-source substitutions were rejected. These checks observe
this test process and Plan; they do not authenticate a production producer.

No v4 AWS producer receipt was fabricated for this built-in-only Plan. Production
producer receipt integration and the later opened/executed Plan identity remain
**IMPLEMENTED / UNVERIFIED**, with operational integration **BLOCKED** on a
separately trusted producer/execution boundary. Existing real-Ed25519 synthetic
receipt/evidence negatives cover failure, incorrect signature/key/domain/operation,
source/State/Plan mismatch and missing/UNKNOWN Journal histories. No executor or
automatic production authorization was added.

## Regression, CI and Journal evidence

PR #43's repaired source was exported to WSL with locked Python 3.14.9 dependencies
and tested under an empty environment and `unshare -n`: **3,006 passed / 2 skipped /
57 deselected**. Ruff check and formatting passed. Independent focused probe tests
also passed. The new offline repair's exact-HEAD and post-merge CI IDs/results
are recorded in its GitHub PR and Issue #50, rather than predicted here.

Genuine PR #43 source-HEAD `e72d4e813e834eb3de51e9c777feba29aca983ce` Backend run
**40202561345** succeeded: 3,006/2/57, nine required Ed25519 tests and 102 API
contracts. Infrastructure/package **40202561298** and both candidate jobs
**40202561289** succeeded. These refer to that source HEAD, not later merges.
The initial merge-only HEAD failed the two stale assertions and old baseline
inventory check; those failed runs are not represented as successful evidence.

Fresh local exact-lock audits: `pip-audit==2.10.1` strict/hash-required, npm all
dependencies and npm production dependencies each found **0 known vulnerabilities**.
This is local audit evidence. No new dependency-audit Actions run was triggered
at the old baseline SHA; its previously reported run remains historical evidence.

Existing SQLite tests exercise atomic two-ID reservation, cross-role conflicts,
full-snapshot CAS, four competing processes on one DB, process exit before/after
commit, response loss, UNKNOWN/no-retry, restart, tombstones, corruption, missing
DB, different-identity replacement and a retained floor rejecting older DBs.
New tests cover simultaneous DB/floor rollback and separate-DB scope explicitly.
No power-loss, remote-filesystem, hostile-host, cross-host partition or globally
independent rollback guarantee is inferred. No new distributed system was built.

## Issue #50 acceptance mapping and completion criteria

| Boundary | Status | Owner and concrete remaining completion evidence |
| --- | --- | --- |
| Local Ed25519/v4 grammar and issuance validity | VERIFIED (offline) | PR #52 complete; do not reimplement. Production trust is a separate row. |
| Actual two-version CLI/Provider, six scopes, Mock/schema, package identity | VERIFIED (observed offline scope) | Codex; official signer enrollment and immutable execution are still separate. |
| Git/source/Plan snapshot mutation rejection | VERIFIED (local scope) | Codex; protected execution source, authenticated origin and descriptor-to-execution binding remain unverified. |
| v4 receipt/gate implementation | IMPLEMENTED / UNVERIFIED (production) | Codex + approved producer owner: observe trusted signer, actual CLI/Provider/source/Plan and subsequent opened Plan in the same protected execution; no production key enrollment authorized here. |
| Local SQLite CAS/ID/UNKNOWN/checkpoint behavior | VERIFIED (single tested DB/filesystem) | Codex; the simultaneous-rollback and separate-DB limits above are demonstrated. |
| Global one-use and independent rollback/uncertainty authority | BLOCKED | Operational owner: choose an independently authenticated, monotonic checkpoint/CAS authority outside DB restore scope; test restored DB+floor, host replacement, response loss and partitions. Provisioning/authentication needs additional approval. |
| Approval/producer enrollment, revocation freshness and trusted time | AUTHORIZATION REQUIRED | User + security owner: approve key registry and revocation policy, authenticate signer/current rights and trusted clock. Local test keys are insufficient. |
| Actual AWS/IAM/State/resource compatibility | AUTHORIZATION REQUIRED | User + AWS operator: fresh scoped Account/Region/resource/SHA read-only approval, real State readback, identity/import/default/upgrader comparisons. None performed here. |
| Formal Plan/Apply/migration/deployment/readiness/adoption | AUTHORIZATION REQUIRED | User + operator: separate exact-SHA/input/State/Plan approvals and independent adoption review; preserve consumed approvals and historical ledgers. PR #43 HOLD release remains explicit. |
| Production cost/monitoring/closure acceptance | NOT STARTED (operational acceptance) | Operational reviewer: approved workload/cost scope, monitoring and Closure evidence tied to the future exact Plan/readback. Existing Mock suites do not complete this gate. |

Minimum external authority properties: one shared approval/attempt ID namespace,
atomic conditional reservation and durable uncertainty before execution, no retry
on missing/unknown outcomes, authenticated current signer/time policy, monotonic
independent checkpoint and append-only receipt retention. Service selection and
provisioning are intentionally deferred; a second SQLite file beside the first
does not satisfy this boundary. Host/path protection and cross-host proof are
external assumptions until tested against an approved implementation.

No AWS authentication/STS/OIDC/API, remote State, real IAM, formal Plan/Apply,
production key operation, readiness change, Ruleset change, deployment or paid
inference was performed. Public release is not READY. Keep Issue #50 OPEN.

Official references checked: [Terraform init](https://developer.hashicorp.com/terraform/cli/commands/init),
[filesystem mirrors](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation),
[built-in terraform_data](https://developer.hashicorp.com/terraform/language/resources/terraform-data),
[Python descriptor flags](https://docs.python.org/3.14/library/os.html#os.O_NONBLOCK).

## Current HEAD recheck (2026-10-26 JST)

The handoff was behind existing work. GitHub was checked again: main is
`bac4263cb86ebeafef944f1110530efa90138ce8`; PR #53 is already MERGED, and held
PR #43 source HEAD `b7d9a3f456a0af53c803bf8cf94784791a68503f` already contains
that main through an ordinary merge. PR #51/#52 signature/snapshot repairs and
PR #53's probe repair are preserved. No reimplementation, force push, additional
merge or HOLD release was needed. Only PR #43 is open. Issue #39 is CLOSED;
Issue #50 remains OPEN. Main's formal pin is still 1.14.9.

All existing worktrees/branches were inventoried. Four existing worktrees had
uncommitted files, including five entries in the original workspace; none was
modified. This recheck used a new managed worktree and a separate disposable
Linux export. The two ChatGPT-owned signature files remain unchanged.

### Fresh observations at the source HEAD

Both real CLIs again passed six backend-disabled, readonly-lock init/validate
scopes and 69 Mock cases each (bootstrap 10, service 57, frontend 2). Provider
6.70.0 schemas were compared against 6.64.0/6.65.0 for all 41 used resource types.
The existing probe was reused, with the same CLI/Provider/package-inventory
SHA256 values in the table above. `/proc` observations of actual CLI and Provider
executables again matched these hashes. Execution used `env -i`, empty child
HOME directories, filesystem mirrors and `unshare -n`; `socket.if_nameindex()`
reported only `lo`. No AWS credentials or remote State were used. The disposable
six-scope source/locks remained unchanged. These observations do not freeze a
future executable or prove State/default/import/upgrader compatibility.

Focused probe/SQLite/snapshot/evidence-gate/approval/Ed25519 tests: **135 PASS**.
Source-to-Plan v4, migration and held-candidate contract tests: **142 PASS**.
Ruff check and format check: **PASS**, 249 files. This is a local focused run,
not a fresh local full-suite run. Genuine source-HEAD Backend CI below supplies
the full regression result. Existing tests cover the v2/v3/v4 boundaries; their
old/new evidence rejection was retained without expanding accepted versions.

A fresh disposable built-in `terraform_data` root produced a real local saved
Plan: **1,534 bytes**, SHA256
`fd9a3510b3650fc558dbe5fae1166f68822d1faf0bad3ed3784531df7a294613`.
Process completion, snapshot bytes, `show -json` and source agreement passed;
Plan/source replacements were rejected. The original Plan was retained privately
before the negative checks. It used no AWS Provider/resources and was not applied.
The local harness's initial syntax/reporting failures were corrected in separate
disposable directories; no failed harness output is counted as successful proof.
No trusted AWS producer receipt or subsequently executed Plan identity is claimed.

### Vendor signature verification added

Previously, this report had only HTTPS checksum agreement. Fresh public checksum
signatures and the public release key were retrieved before isolation. GnuPG
2.4.4 verified all three checksum signatures in a new temporary keyring, with no
auto key retrieval, inside the isolated namespace. Each `VALIDSIG` reported signing
subkey `374EC75B485913604A831CC7C820C6D5CD27AB87` and primary fingerprint
`C874011F0AB405110D02105534365D9472D7468F`. The primary fingerprint was matched
against [HashiCorp's official security publication](https://www.hashicorp.com/en/trust/security#pgp-public-key)
and its [2026 key-expiry update](https://discuss.hashicorp.com/t/hcsec-2026-03-hashicorp-gpg-key-72d7468f-update/77237).
No production key registry or system keyring was changed.

| Signed checksum file | Signature date (UTC) | Archive/binary agreement |
| --- | --- | --- |
| terraform_1.16.7_SHA256SUMS | 2026-10-22 | Linux ZIP hash and extracted CLI match the measured executable |
| terraform_1.17.0_SHA256SUMS | 2026-10-21 | Linux ZIP hash and extracted CLI match the measured executable |
| terraform-provider-aws_6.70.0_SHA256SUMS | 2026-10-22 | Linux ZIP hash and extracted Provider match the measured executable |

This verifies release signatures and exact archive-to-binary bytes against the
vendor key published over official HTTPS. It does not establish an independent
out-of-band trust ceremony, organization-approved trust enrollment/revocation
freshness, trusted time or immutable loaded-code attestation. The existing probe's
`official_signer_authenticated=False` remains truthful: the probe does not itself
perform signature verification. This separate signature evidence does not alter
that API or grant execution authority. Native Windows CLI version/platform and
executable hashes were also rechecked in empty directories with allowlisted child
environments; both match the earlier values above. This was not a native network
isolation/Provider test; Windows Provider execution remains untested.

### Genuine Actions and review evidence

All four PR workflows at source HEAD `b7d9a3f` completed successfully:

| Workflow | Run | Verified scope |
| --- | --- | --- |
| Backend | [40203976514](https://github.com/yonegen0/ai_interview/actions/runs/40203976514) | 3,006 passed / 2 skipped / 57 deselected; Ed25519 9; API contracts 102; Ruff check/format |
| Frontend | [40203976537](https://github.com/yonegen0/ai_interview/actions/runs/40203976537) | Frontend verify SUCCESS |
| Infrastructure/package | [40203976539](https://github.com/yonegen0/ai_interview/actions/runs/40203976539) | terraform, package_changes and actual package jobs SUCCESS |
| Candidate matrix | [40203976534](https://github.com/yonegen0/ai_interview/actions/runs/40203976534) | Both real CLI jobs SUCCESS |

Main `bac4263` push runs are also SUCCESS: Backend 40203945696, Frontend
40203945837, infrastructure 40203945739, candidate matrix 40203945591.
The last dependency-audit Actions remains **40197182297** at `4e5a23c`; it is
historical, not evidence of a newly run audit at either current SHA. The workflow
has no manual-dispatch trigger, and no dependency files changed. Earlier local
zero-vulnerability audits are retained as earlier observations, not fresh results.

The active `main-pr-and-ci` Ruleset has five required checks, strict base matching,
review-thread resolution, no force push/deletion and no bypass actors. There is no
separate classic branch-protection object; that 404 does not negate the Ruleset.
PR #43 has no unresolved inline review threads. Prior independent source review
and the corrected PR #53 rollback test are reused for unchanged source; this
recheck is a self-review, not a new independent production-adoption review.
Although this successor changes only documentation, PR path filtering considers
the cumulative diff against main, so the held PR's candidate matrix also runs.
Source, Terraform and dependency bytes are unchanged. Successor HEAD CI IDs are
recorded on PR #43 and Issue #50 after completion, rather than predicted here.

### Remaining acceptance work and ownership

| Acceptance condition | Current classification | Owner, completion evidence and additional approval |
| --- | --- | --- |
| Local signatures including PR #52's issuance validity, snapshots, CLI/Provider identity, six scopes and schema/Mock qualification | VERIFIED (offline scope) | Codex; no further offline code defect reproduced. Vendor signature verification above completes the public-release signature check only. |
| Local CAS, four-process same-DB competition, cross-role IDs, tombstones, crash/UNKNOWN, restart and retained-checkpoint rollback rejection | VERIFIED (tested local DB/filesystem) | Codex; DB+checkpoint rollback and separate-DB reuse are explicit demonstrated limits, never authorization/retry. |
| Protected source/loaded-code execution and trusted producer receipt through later opened/executed Plan | IMPLEMENTED / UNVERIFIED | Codex + execution owner; exercise an independently protected producer/signer with exact CLI/Provider/source/Plan bytes and later opened Plan. Production trust/provisioning requires approval. |
| Independent checkpoint and cross-host global one-use/CAS | BLOCKED | Operational owner; approve/select an authenticated monotonic authority outside DB restore scope, then prove restored DB+floor, host replacement, response loss and partition behavior. External provisioning/authentication needs approval. SQLite-only tests cannot close this row. |
| Production approval/producer keys, revocation freshness and trusted time | AUTHORIZATION REQUIRED | User + security owner; authenticate/enroll keys, current authority, revocation policy and time under a separately approved policy. Vendor PGP verification is a different boundary. |
| AWS/IAM/State/resource compatibility | AUTHORIZATION REQUIRED | User + AWS operator; fresh Account/Region/resource/SHA read-only approval, identity/State/default/import/upgrader/readback evidence. No AWS operation was performed. |
| Formal Plan/Apply/migration/deployment/readiness/candidate adoption | AUTHORIZATION REQUIRED | User + operator; separate exact-SHA/input/State/Plan approvals and explicit PR #43 HOLD release. Existing approvals are not reusable. |
| Production cost/monitoring/Closure acceptance | NOT STARTED (operational acceptance) | Operational reviewer; approve workload/cost scope, observe monitoring delivery and Closure on future exact Plan/State. Desk review below is complete, but cannot satisfy live acceptance. |

The desk review mapped the existing runbook and
[approval template](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md) to future acceptance:
retain approved budget/workload and Worker concurrency 2; budget alerts are not
a hard spend cap; verify Alarm/SNS delivery under approved synthetic inputs;
require four specific closure directions and only approved validation-Alarm
deletions; preserve code/alias/Artifact; require State/AWS readback and no lock or
outside-State resources. Partial failure/unknown/State mismatch forbids an
unapproved retry or forced Closure. These are existing gates, not new approval.
No live cost/monitoring/Closure result is inferred from a schema or Mock test.

Private raw recheck evidence was retained separately under
`C:/Users/user/.codex/issue50-head-audit-20261026` and
`/root/issue50-head-audit-20261026`; no Plan/State/private ledger is committed.
No AWS authentication/API, IAM/Ruleset/readiness mutation, remote State, formal
Plan/Apply, production key operation, deployment or paid AI inference occurred.
Issue #50 stays OPEN and PR #43 stays Draft/HOLD.
