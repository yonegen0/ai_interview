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
