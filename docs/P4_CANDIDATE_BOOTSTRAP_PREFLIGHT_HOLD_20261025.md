# Issue #39 — candidate bootstrap offline preflight (HOLD)

This is **candidate-only, non-executing preparation**. It does not adopt Terraform
1.16.7 / AWS Provider 6.70.0, enable maintenance/recovery, perform Terraform
validation, authenticate AWS, read State, or authorize Plan/Apply.

## Separation of execution contracts

- Existing formal and historical bootstrap maintenance/recovery paths remain
  unchanged at Terraform **1.14.9**, including their old approval and receipt
  schemas. The new module is not imported by either execution controller.
- The proposed candidate execution namespace is
  `p4-bootstrap-candidate-1.16.7-aws-6.70.0-linux_amd64-v2`.
  Terraform **1.17.0** is offline qualification only, not an approved candidate
  bootstrap runtime.
- `backend/skills/p4/candidate_bootstrap_preflight.py` accepts exact v2
  synthetic/local manifests, six HCL requirements and six provider locks,
  Terraform version JSON, a binary digest, State identity, a separate approval,
  and a NEW attempt journal. Apply/recovery additionally require a same-namespace
  saved Plan manifest, matching binary bytes and distinct Plan approval.
- Mismatched versions, provider selections, platform, namespace, identity,
  approval, plan hashes, missing fields, extra fields, and FAILED/UNKNOWN
  attempt states fail closed.
- Successful return means only
  `OFFLINE_CANDIDATE_PREFLIGHT_ONLY`, `authorized: false`, `aws_operations: 0`.
  There is deliberately **no CLI main, Terraform subprocess, SDK client,
  backend initialization or execution path**.

## Unproven security and operational properties

This pure validator cannot attest that JSON was genuinely emitted by a
specific Terraform binary; that the binary checksum came from an official
source; that official provider package hashes cover the local platform; that
a saved Plan was created with the claimed CLI; that any hash/approval is
signed, fresh or unforgeable; that the journal is atomically durable; or that
real State/upgraders/defaults/API Gateway/SNS identities are compatible.
In particular, a matching synthetic Plan manifest **does not prove** the
saved binary's producing runtime or allow it to be applied.

The HCL version-token checks are not Terraform syntax validation. Any future
real execution controller must independently implement **all** of these gates
before AWS authentication and before attempt consumption:

1. Immutable Git/source/review identity and exact candidate source bytes.
2. Official checksums, Terraform version/platform and provider installation
   checks; sterile `init -backend=false` and `validate` on a disposable
   checkout, with no credentials, before SDK access.
3. Authenticated, expiry-bound, one-use approvals tied to the entire CLI,
   Provider, platform, HCL, original State version/lineage/serial/hash,
   immutable Plan bytes and fresh review evidence.
4. Separate idempotent failure/UNKNOWN journals and explicit no-retry rules
   that survive process crash and partial success.
5. Independent operating/security review and real AWS/State/provider
   readback after **separate authorization**. Candidate-only checks do not
   satisfy the HOLD-release or Apply authorization boundary.

All remote State access, formal Plan/Apply, AWS, paid inference, Environment
readiness and PR #43 merge remain **HOLD**. Do not invoke historical
controllers with candidate evidence or reuse historical Plan binaries,
approvals, receipts, or ledgers.


## Supplementary offline evidence review (Issue #39 follow-up)

Two **non-executing** candidate-only modules extend the existing preflight without
changing `bootstrap_maintenance.py`, `bootstrap_recovered_apply.py`, their
approval schemas, Terraform requirements or any AWS permissions.

- `candidate_offline_controller.py`: SHA-256 inventory of **all supplied
  tracked Terraform files** (rather than only the twelve candidate version/lock
  files), comparison of preflight configuration bytes to this inventory, exact
  candidate namespace / source / approval / attempt bindings, UTC-aware
  one-hour maximum review interval and expiration rejection. A signed and
  independently authenticated Git commit/tree is still required to establish
  the legitimacy of `tracked_paths` and `checkout_files`. The v3 review
  descriptor is **not a genuine signed approval**, and review success always
  returns `authorized=false`.
- A Linux-only, private local create-only reservation helper writes and fsyncs
  the approval marker **before** the attempt marker. Reuse fails, and a crash
  between those writes permanently freezes that approval. Stored
  `STARTED_UNKNOWN_ON_RESTART` markers must never be interpreted as permission
  to retry. This is local best-effort persistence, **not** a tamper/rollback
  proof, a distributed lock, or an approved operational journal. It does not
  contact AWS or start Terraform; future real controllers cannot use it as a
  substitute for a separately reviewed immutable ledger.
- `candidate_offline_controller.py` additionally exposes a **read-only local Git
  SHA-1 repository/checkout inspection helper**: fixed HEAD commit and tree,
  exact recursive tracked `terraform/` blobs, regular-file modes, no symlinks,
  no untracked/ignored extra Terraform files, all six required scopes, and full
  SHA-256 inventory. Synthetic Git repositories exercise tampering, missing
  files, untracked HCL, wrong HEAD and symlink rejection. This does **not**
  authenticate the Git origin, commit signer, executable Git binary, or
  reviewed-commit provenance, and it does not provide atomic/TOCTOU-safe
  execution snapshots. Actual source-to-saved-Plan origin remains unproven.
- Candidate saved-Plan descriptors now reject mismatched plan operations both
  ways: `maintenance-apply` requires `maintenance-plan`, whereas
  `recovery-apply` requires `recovery-plan`. Matching descriptors alone never
  authenticate Plan-producing CLI or allow an Apply.
- `candidate_state_snapshot_review.py`: JSON Plan major-1
  `format_version` check, raw State duplicate-key/non-finite rejection,
  synthetic/raw-local State JSON digest,
  lineage, serial, raw State format-v4 checks, JSON resource schema presence,
  deferred and unsupported action rejection, proposed/after unknown-mask
  validation and sensitivity-metadata syntax checks. The review delegates
  no-op pair comparison to existing `toolchain_compatibility.py`, leaving its
  existing behavior unchanged. Synthetic API Gateway identity and SNS default
  values remain review fixtures, not proof of real provider behavior.
  The claimed S3 VersionId is **not independently validated** by this library.

HashiCorp's JSON output specification requires consumers to handle
`proposed_unknown`, `after_unknown`, `sensitive_values` and JSON
`format_version` deliberately. A provider lock's `h1:`/`zh:` entries are
checksum *formats*; their syntactic presence does **not** authenticate provider
packages or signer trust. References:

- https://developer.hashicorp.com/terraform/internals/json-format
- https://developer.hashicorp.com/terraform/language/files/dependency-lock
- https://developer.hashicorp.com/terraform/cli/commands/show

## Still HOLD: no transition from candidate-only review to execution

The new supplementary modules intentionally do not construct or launch a
candidate maintenance/recovery controller; no bridge to real AWS or Terraform
exists. Critical unproven prerequisites remain:

1. Independently verified Git source identity, complete authenticated tree and
   executable controller code identity, without untracked or changed bytes.
2. Official Terraform 1.16.7 checksum/platform provenance, AWS Provider 6.70.0
   official package/signature checks, real binary `version -json`, complete
   parser-based HCL checks and sterile disposable `init -backend=false` /
   `validate` before AWS authentication.
3. Fresh, independently signed/verified one-use execution approvals and
   separate maintenance-plan, maintenance-apply and recovery-apply grants,
   with immutable commit / binary / State / saved-Plan / configuration binding.
4. Independently approved **remote** atomic attempt and approval journal
   semantics, including crash, timeout, partial success and UNKNOWN freeze;
   durable local files alone cannot authorize action.
5. Separate AWS read/Plan/Apply authorizations, real remote State
   VersionId/lineage/serial/hash readback, actual provider schema/state upgrader
   qualification and an independent SHA-fixed code review.

A successful GitHub CI run and synthetic JSON test provide **no real AWS State
or Apply-safety guarantees**. PR #45 and PR #43 remain Draft/HOLD, Issue #39
remains OPEN and formal Terraform remains 1.14.9.

## Codex independent offline verification (2026-10-25)

The original eight-file change at `184ebab29fcde3374c5e6620b6bba72c5c1a1099`
received an independent code review plus actual network-isolated Linux CLI,
official package checksum, six-scope disposable configuration and filesystem
fault verification. See [the independent review report](P4_CANDIDATE_INDEPENDENT_REVIEW_20261025.md)
for the five reproduced P2 findings, minimal fixes, tests and explicit limits.
Codex's new fixes received self-review, not a second independent review.

Candidate-only fixes reject deferred action invocations, contradictory change
identities, structural-metadata re-entry inside unknown attribute masks and
static linked root ancestors. Marker creation now pins its final directory
before writing, preventing the reproduced parent-symlink redirected write.
This does not freeze all ancestors or make a local ledger tamper/rollback proof.
Owner deletion/root replacement still allows local re-reservation; operational
execution must not rely on that local reservation as authority.

PR #45's tracked Terraform remains the legacy contract. Positive candidate CLI
tests used an explicitly identified disposable PR #43 requirement/lock overlay;
the unchanged legacy source correctly rejected both candidate CLIs. Official
HTTPS checksum/content-hash matches were checked; detached signer trust and real
AWS State compatibility were not established. PR #43/#45 remain Draft/HOLD and
Issue #39 remains OPEN, including after successful local tests or new-HEAD CI.
