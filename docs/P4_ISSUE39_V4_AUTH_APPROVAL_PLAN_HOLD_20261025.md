# Issue #39 — v4 signed approval and source-to-Plan offline contracts

**OFFLINE_ONLY / NON_AUTHORIZING / Draft / HOLD — 2026-10-25 JST.**

This stacked increment starts at PR #47 HEAD `62e13d5f397ef4e54efd62cb879bbbfff2f7b9f0`, following PR #46 -> #45. PR #43 remains a separate candidate upgrade HOLD. No existing controller, Journal repository or execution adapter is modified. Formal Terraform remains 1.14.9. No AWS, real State, signing-key enrollment, Terraform Plan/Apply or readiness mutation was performed.

## Files and interfaces

- `candidate_signed_approval.py`: new **v4-only** approval envelope with fixed schema, operation, namespace, review/trust revision, issuer/key ID, account/Region/resource scope, execution/cost limits, source commit/tree/inventory, configuration and lock, CLI/version/binary, Provider version/inventory, State identity, Plan SHA, approval and attempt IDs, and strict issuance/expiry. The canonical format is an explicitly restricted **ASCII/string/non-negative integer/null JSON profile** with sorted keys and no whitespace, domain prefix `ai_interview:p4:candidate:approval:v4\x00`; **NOT RFC 8785 JCS**. UTF-8 duplicate keys, floats, non-finite values, missing/excess fields, type aliasing and malformed Base64 fail closed.
- `TrustedKey` is a **caller-provided policy object, not trusted enrollment**. It pins exact public key bytes, issuer, operations, namespace, revision, validity and revocation. Unknown/revoked/expired keys reject. Missing trust registry yields `UNVERIFIED_HOLD`. A locally verified Ed25519 signature yields `signature_verified=True`, but `trust_enrollment_authenticated=False`, `clock_authenticated=False`, `origin_authenticated=False`, and `authorized=False`.
- `candidate_source_plan_v4.py`: validates exact source/CLI/Provider/State/Plan-byte hashes, maintenance/recovery operation pairing, two distinct approval IDs and two distinct attempt IDs, plan-vs-apply approval claims, and a strictly shaped synthetic generation receipt. A caller-supplied receipt **cannot** attest a Terraform producer. All success results retain `origin_authenticated=False`, `state_readback_verified=False`, `authorized=False`.
- Two new negative regression modules test malformed and tampered envelopes, key mismatch, bad signatures, TTL, replay, ID role confusion, source/inventory/lock changes, plan replacement, cross-operation approvals and UNKNOWN/HOLD.

## Crypto deployment dependency and limits

The current `backend/pyproject.toml`/`backend/uv.lock` do **not** contain `cryptography`. To avoid manually fabricating lock hashes or a security-sensitive supply-chain change, this PR does **not** edit dependencies. Verification imports maintained `cryptography` only *after* schema/registry/policy checks; in an environment without this dependency, an enrolled-key verification attempt fails with `CandidateSignedApprovalCryptoDependencyMissingHOLD`. New tests run real ephemeral Ed25519 sign/verify when the dependency is installed, and explicitly assert fail-closed behavior when missing; CI success without the dependency **does not mean** Ed25519 verification was exercised there. A separately reviewed dependency/lock/CI update is mandatory before production adoption. No real keypair is generated or enrolled by application code.

A clock passed by caller is not independently trusted; neither a registry supplied by an untrusted caller nor an unverified Git origin is a trust root. Production enrollment, revocation freshness, rollback checkpoint, signed producer receipt, actual approval-to-ID linkage, exact loaded binary/provider, frozen source snapshot, State readback, durable globally atomic journal and separate operational release are **all HOLD**. These pure functions must not be wired into a privileged controller as an authorization predicate. No old v2/v3 signatures or approvals are upgraded.

## PR #47 independent file-by-file review (read only)

1. `backend/skills/p4/candidate_journal_model.py`: single-object lock serializes combined ID reservation and complete-snapshot CAS. Synthetic before/after-commit response losses return indeterminate errors; cloned inputs/history prevent caller writes. **No new concrete P1/P2 found in this limited model**. **P1 integration risk, already documented:** new repository instances and lost pre-commit responses offer no durable global anti-replay or host-wide HOLD; Codex owns persistent enforcement, so this file is not edited here.
2. `backend/tests/unit/test_candidate_journal_model.py`: includes concurrent collisions in both role directions, partial-ID failure, stale CAS, UNKNOWN and terminal refusal, response loss and detached-instance counterexample. **P2 coverage gap:** no real multi-process, crash-power-loss or persistent transaction simulation; tests explicitly model only shared-process memory. Codex owns persistent adapter and real fault injection. No tests removed or weakened.
3. `docs/P4_CANDIDATE_TRUST_AND_DURABLE_JOURNAL_DESIGN_20261025.md`: design clearly distinguishes official source/signers, key enrollment, rollback witness and Plan-producer evidence from Mock guarantees. **P2 open integration prerequisites**, not claims of implementation. No edits due to Codex ownership.

## Integration conditions

- Keep PRs #43/#45/#46/#47 and this PR **Draft/HOLD**, Issue #39 OPEN; no merge or Ready without explicit user permission.
- Before enabling any execution, Codex must independently establish durable common namespace one-use keys, crash/timeout UNKNOWN persistence, a separately witnessed rollback checkpoint, signed producer receipt, authenticated immutable checkout, actual CLI and Provider binary provenance, and real State/AWS compatibility under separate authorization.
- Plan approval always binds `plan_sha256=null`; Apply approval binds the exact generated Plan SHA. Approval and attempt identifiers cannot be reused across roles. **A signature is not execution authorization.**
- Production endorsement requires independently authenticated trust enrollment and trusted time, pinning `cryptography` in the Python 3.14 uv lock, testing the exact CI wheel and Ed25519 official vectors, and independent security review of canonical byte interoperability.

Validation and genuine CI run IDs are reported in the PR body after execution; all unfinished checks remain **UNVERIFIED**.
