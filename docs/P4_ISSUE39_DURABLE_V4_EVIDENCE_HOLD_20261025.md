# Issue #39: durable local Journal and v4 evidence integration

**OFFLINE_ONLY / NON_AUTHORIZING / Draft / HOLD.** No execution authority, merge,
candidate adoption or HOLD release. Issue #39 stays OPEN. Formal Terraform remains
1.14.9. This increment is stacked on PR #48, exact base
`1a683f376a4b78c0b8de3002d24ff8186f266a05`.

## Implemented boundaries and file review

| Files | Change / priority addressed | Tests / remaining limit |
| --- | --- | --- |
| `backend/skills/p4/candidate_journal_sqlite.py` | P1: explicit create/open, pinned DB identity, FULL synchronous transactions, atomic two-ID tombstones and NEW/RESERVED events, full-snapshot CAS, operation pin, append-only SQL triggers, hash chain, checkpoint floor, uncertainty poisoning, one-transaction related reads | `test_candidate_journal_sqlite.py`: restart, threads, four independent processes, cross-role/Plan-Apply collisions, stale CAS, commit-boundary process exit, lost responses, synthetic I/O errors, incomplete/truncated/corrupt DB, schema-restored tamper, rollback, UNKNOWN and invalid IDs. Scope is one DB on one local filesystem. |
| `backend/skills/p4/candidate_producer_receipt.py` | P1: distinct-domain Ed25519 producer receipt, algorithm/key/revision/window, explicit signed Plan operation, shared source/toolchain/State/scope/limits, actual Plan digest, receipt self-digest with its field omitted | Integrated tests sign using fresh synthetic keys. Key enrollment and a real Terraform producer remain unverified. |
| `backend/skills/p4/candidate_evidence_gate.py` | P1: complete v4 approval bindings/signatures, producer envelope, exact supplied Plan bytes, actual local Plan COMPLETED and Apply RESERVED histories at one DB checkpoint | `test_candidate_evidence_gate.py`: accepted local evidence still HOLD; altered Plan, signatures, key absence, receipt domain/digest/State/operation and Journal source/operation/missing/UNKNOWN rejected or HOLD. No execution callback or trusted-boolean override. |
| `backend/skills/p4/candidate_artifact_snapshot.py` | P1: reuse existing real Git blob/inventory checks, immutable Python byte tuples, double observation, directory identity check; bounded no-follow/nonblocking Plan read and digest | `test_candidate_artifact_snapshot.py`: actual disposable Git repositories, mid-capture extra file, changed files, identical-content checkout replacement, Plan substitution/empty/oversize/symlink. Linux functionality; unsupported no-follow platforms explicitly HOLD. No future execution snapshot guarantee. |
| `backend/skills/p4/candidate_toolchain_probe.py` | P1: require separate Linux network namespace with only loopback; exact binary/package pins; internally generated disposable HCL, empty HOME and allowlisted environment; filesystem mirror only; fixed version/init-without-backend/validate/schema commands | `test_candidate_toolchain_probe.py`: namespace/interface and pre-execution binary/version/lock rejection. Real two-version probe separately described below. No Plan/Apply or repository backend. |
| `backend/pyproject.toml`, `backend/uv.lock` | P1: pin `cryptography==50.0.2` using uv 0.13.5, retaining other installed package versions; lock-generated cffi 2.1.1 / pycparser 3.12 | `uv sync --locked` succeeds on Windows and Linux Python 3.14.9. No manual lock hashes. |
| `backend/tests/unit/test_candidate_ed25519_required.py`, `.github/workflows/backend.yml` | P1: unconditional cryptography import, RFC 8032 7.1 TEST 1/2/3 sign/verify plus mutated message/signature, v4 operation/domain/message/key negatives; explicit mandatory CI step | 9 real crypto tests, no dependency-absent success path or skip. Existing optional-dependency regression remains intact. |
| `backend/skills/p4/build_lambda.py`, `backend/tests/unit/test_candidate_package_crypto.py` | P2: exclude only the pinned cryptography wheel's exact non-runtime `cryptography/hazmat/bindings/_rust/test_support.pyi` from Lambda ZIP and filtered RECORD | Five regressions verify deterministic omission and retained rejection of executable/sibling/source test files and symlinks. No general test-path exception. |

Self-review also corrected a SQLite connection leak (SQLite context managers do
not close connections), ensured related Journal reads share one checkpoint,
rechecked uncertainty after acquiring the write lock, rejected bool/recursive
expected producer payloads, and prevented unsupported no-follow access from
raising an unclassified AttributeError. Probe development rejected its initial
incomplete Provider package; including the official LICENSE plus executable and
pinning their inventory restored the official lock's package checksum agreement.
No existing tests or v2/v3/v4 validators were deleted, skipped or weakened.
This is self-review, not an independent security review.

## Local validation

- Python **3.14.9**, cryptography **50.0.2**, uv **0.13.5**.
- Windows: real crypto and SQLite/process tests; Linux WSL: full regression with
  empty environment, isolated HOME, fixed Node 22.23.4 PATH and `unshare -n`.
- First full Linux snapshot: **2,906 passed / 2 skipped / 57 deselected**.
  Final regression: **2,921 passed / 2 skipped / 57 deselected** (66.85s), including
  15 further probe/input/related-read cases. Matching commit/Actions IDs belong
  in the PR body. The 75 new cases comprise SQLite 35, crypto 9, integration 15,
  snapshots 8 and probe boundaries 8.
- Initial Ruff check and **247-file** format check PASS; `git diff --check` PASS.
- No newly added test skip. Existing two Linux skips remain existing behavior.
- Side-effect tests deny socket connect, subprocess creation and boto3 client
  creation in evidence/Journal paths. Git and crash/competition tests intentionally
  use local subprocesses. All full-regression children run without external
  networking. Dependency/public archive downloads occurred separately, before
  isolation; none contacted AWS.

Initial current-HEAD Actions at `4b08ea3` exposed a packaging failure:
run **40193865786**, job **121170431312**, `Build from locked production
requirements`, `contents/UnsafePackageContent`. The pinned crypto wheel includes
the official test typing stub cited above. It is now omitted rather than allowed
into the package; safety rejection remains for similar executable/other/source
paths. Targeted package/previous packaging/required-crypto regression:
**52 passed**. Total new cases after this fix: **80**. Ruff format now checks
**248 files**. Final new-HEAD full regression, package build/import and CI results
belong in the PR body; the failed older run is not new-HEAD success evidence.

## Actual disposable Terraform / Provider probe

Fresh official HTTPS archives agreed with freshly retrieved SHA256SUMS. Their
members supplied the probe's exact binary and package pins. Candidate locks were
read from PR #43's Git object (`789dfa2`), never from remote State. No tracked
Terraform configuration or lockfile changed.

| Product / linux_amd64 | ZIP SHA256 | Executable SHA256 |
| --- | --- | --- |
| Terraform 1.16.7 | `5454efcf7fc87f0c2113111b9a5c7182f0ca1c6f0f23a1e110a50770a8fe473b` | `54533008a91f4aa992bb530963f6a902f67f4cf75245c014cdf57df4afb8d2ec` |
| Terraform 1.17.0 | `c168cab7c637a8769fdb90089ddd19de701bc6ff8aca64dc2e2185fe46f59f67` | `664b66cc0bcd7ed28fd27569719ccaa8a40c230b8be45060ce4d65e2852e1bcc` |
| AWS Provider 6.70.0 | `58acc041b080778ded75320e241ebcf6cf2ed145bede644b86a4784ce46086c6` | `75d70f99d54bbef98e8f200ff0df71d2147e309cf46269a21eabf9c3842f7183` |

Provider inventory (LICENSE + executable, sorted filename-to-SHA256 JSON):
`27f68be7b1584292b4339708a5546bc7217bbc434dc780a71016b04a06361728`.

Both versions passed `version -json`, `init -backend=false -input=false
-lockfile=readonly -get=false`, `validate -json` and `providers schema -json`.
The fixed commands ran in new disposable directories with no backend, resources,
data sources, credential files or credential environment; the network namespace
contained only loopback. Source/lock/binary bytes were rechecked and no State file
was created. Wrong CLI digest, Provider digest, lock version and claimed CLI
version were rejected. These are local observations, not official signer trust,
loaded-code attestation, adoption evidence or real State/AWS compatibility.

## Independent HOLD conditions

| Component | Status |
| --- | --- |
| Approval v4 real Ed25519 and formal uv dependency | IMPLEMENTED / locally TESTED; matching-HEAD CI required |
| Producer receipt signature contract | IMPLEMENTED / synthetic real-crypto TESTED; actual producer and independently enrolled/revocable key UNVERIFIED / HOLD |
| Source-to-Plan + persistent local history gate | IMPLEMENTED / TESTED; NON_AUTHORIZING |
| Local SQLite one-use/CAS/restart/competition | IMPLEMENTED / TESTED on one database; cross-host global authority UNVERIFIED / HOLD |
| Rollback checkpoint | Caller-held floor comparison TESTED; independent rollback-resistant checkpoint UNVERIFIED / HOLD |
| Git source / Plan snapshots | Local byte/change checks TESTED; Git origin and immutable execution/opened-Plan binding UNVERIFIED / HOLD |
| Terraform/Provider | Official HTTPS archive checksum agreement and isolated CLI use TESTED; PGP signer and immutable loaded toolchain UNVERIFIED / HOLD |
| State identity | Structural equality TESTED; actual readback/compatibility UNVERIFIED / HOLD |
| Key enrollment/revocation, clock, signer authority | UNVERIFIED / HOLD |
| New operational approvals, independent review, user HOLD release | Required; not granted |

SQLite triggers/hash chains cannot stop an owner replacing or coherently rewriting
the entire DB. An externally retained floor detects rollback behind that floor;
a DB and checkpoint rolled back together cannot. After a crash before the first
commit there can be no durable attempt record. The local client freezes after a
reported unknown outcome, but a newly constructed client is not a persistent
authority for an absent outcome. This increment deliberately has no executor;
absence never permits execution retry. A future controller needs independent
durable uncertainty and rollback authority before any operational use.

`os._exit` before/after commit, static truncation and injected OSError are tested.
Actual power loss, controller cache failure, hardware torn-sector writes, remote
filesystems, multi-host partitions and hostile simultaneous ancestor replacement
are not proven. Local Journal path checks do not establish a protected host or
filesystem. These limits remain HOLD regardless of CI success.

P1 next offline work: protected producer/source/toolchain execution snapshots and
an independently reviewed durable authority/checkpoint protocol. Key enrollment,
trusted clock/revocation and operational policy need an independent trust root.
AWS/STS, remote State, formal Plan/Apply, IAM/OIDC/readiness/Ruleset changes,
deployment, paid inference, Ready/merge and HOLD release require separate user
authorization and were not performed.

## Official references checked 2026-10-25 JST

- [cryptography 50.0.2 installation](https://cryptography.io/en/50.0.2/installation/),
  [release/security notes](https://cryptography.io/en/50.0.2/changelog/),
  [official Python 3.14 metadata](https://pypi.org/pypi/cryptography/50.0.2/json),
  [Ed25519 API](https://cryptography.io/en/50.0.2/hazmat/primitives/asymmetric/ed25519/).
- [RFC 8032 section 7.1](https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1).
  The constrained v4 canonical profile is not RFC 8785 JCS; other-language
  signer interoperability remains unverified.
- [Python 3.14 sqlite3](https://docs.python.org/3.14/library/sqlite3.html),
  [SQLite atomic commit and failure assumptions](https://sqlite.org/atomiccommit.html).
- [Terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate),
  [filesystem provider mirrors](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation).

Original working-directory edits and all existing worktrees/branches were
preserved. New work uses `codex/issue39-v4-durable-20261025`. PRs #43/#45/#46/#47/#48
remain OPEN Draft/HOLD and Issue #39 OPEN. Do not reuse their old CI as evidence
for this increment; exact new-HEAD runs belong in the new Draft PR body.
