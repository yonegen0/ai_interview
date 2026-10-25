# PR #46 independent offline security review — 2026-10-25 JST

**Draft / HOLD; OFFLINE_ONLY / NON_AUTHORIZING.** This review does not approve
Terraform adoption, execution, AWS/State access, release, or merge.

## Independence and exact scope

A separate review agent inspected all six PR #46 files in an isolated detached
worktree, first at `6ab1649e0f4184c7fa77fbd62732814dae272d30`, then at integration
commit `2876ffe` plus the implementer's six-file working diff. The reviewer did
not implement the fixes or modify the implementer's checkout. The original
repository's unrelated uncommitted changes were preserved.

**Final reviewed result:** all four concrete findings below are corrected in
the final six-file diff. No remaining concrete P1/P2 was identified within
this offline validator scope. The operational trust gates below remain HOLD.

| File | Individual review result |
| --- | --- |
| `backend/skills/p4/candidate_approval_contract.py` | The recovery Plan operation was missing. The fix adds `recovery-plan` and requires null Plan hash for both Plan-creation operations; Apply requires an existing hash. Both supplied bindings are checked before comparison. Signature verification and issuer/key trust remain explicitly unverified. |
| `backend/tests/unit/test_candidate_approval_contract.py` | Inspected schema, operation/namespace, field and State identity mismatch, evidence, expiry/clock and non-authorizing tests. New tests cover both Plan and Apply operation families and cross-target rejection. |
| `backend/skills/p4/candidate_journal_contract.py` | Original forward revisions bypassed legal transitions. The final fix checks reachable state/revision pairs at the common entry boundary, adjacent transitions, equality only for identical same-revision content, and complete history anchored to both snapshots for gaps. |
| `backend/tests/unit/test_candidate_journal_contract.py` | Inspected terminal states, duplicate IDs, missing/partial/reordered events, time/revision monotonicity, crash HOLD and rollback tests. New first-pass tests exercise all terminal exits, backwards transitions, equal-revision rewrites, missing history and invalid anchors. |
| `backend/skills/p4/candidate_plan_binding.py` | Independently found expected-side State identity numeric type confusion. The fix validates both State identities, rejecting boolean/float serial aliases. Operation mapping, source/tree/inventory/configuration/lock/CLI/State/Plan comparisons and distinct approval ID checks were reviewed. |
| `backend/tests/unit/test_candidate_plan_binding.py` | Inspected wrong-source/toolchain/State/Plan/evidence, operation crossing, approval separation, old schema and no-network/subprocess tests. New tests reject boolean/float serials on the expected side. |

## Findings and reproductions

1. **P2 — recovery Plan approval contract mismatch (fixed in reviewed diff).**
   `recovery-apply` requires `recovery-plan`, while the original approval
   whitelist excluded it. Both Plan creation operations now require
   `plan_sha256=None`; their eventual Apply approvals require the produced hash.
   Plan and Apply approval IDs still require separate durable replay controls.
2. **P2 — forward-revision snapshot resets (fixed in reviewed diff).**
   `COMPLETED(3) -> NEW(4)` and `STARTED(2) -> RESERVED(3)` previously passed.
   Adjacent observations now use the legal transition validator. Gaps require
   a complete, valid supplied history containing both exact snapshot anchors.
   Same-revision content changes and older snapshots remain rejected.
3. **P2 — expected State serial numeric alias (fixed in reviewed diff).**
   A valid Plan with serial `1` was accepted against expected serial `true` or
   `1.0`; serial `0` likewise matched `false` or `0.0`. Python dictionary equality
   treated these unequal JSON types as equal. Both State identity objects are
   now structurally validated before comparison.
4. **P2 — impossible snapshot state/revision pairs (fixed after independent
   follow-up).** The first rollback fix still accepted
   `NEW(3) -> RESERVED(4)`, `RESERVED(100) -> STARTED(101)`,
   `STARTED(100) -> COMPLETED(101)`, and identical `NEW(100)` snapshots without
   history. The non-cyclic transition graph can reach only `NEW(0)`,
   `RESERVED(1)`, `STARTED(2)`, `COMPLETED/FAILED(3)`, and `UNKNOWN(2|3)`.
   The final common `check_entry` boundary now rejects these fabricated
   snapshots before equality, adjacent-transition acceptance or crash handling.

The fourth reproduction was executed with the existing synthetic journal
fixture and `check_snapshot_rollback`; all four invalid examples returned
success at the first-pass snapshot. No Terraform or AWS call was involved.
The final diff adds five fail-before regression cases. Existing crash fixtures
now use reachable revisions; invalid-transition assertions retain rejection
while recognizing the earlier state/revision invariant error. No security
test was deleted or skipped.

## Independent local evidence

- Original six-file scope: **104 passed**.
- First-pass six-file correction snapshot: **144 passed**; Ruff check passed;
  Ruff format check passed for all six files.
- Final six-file correction snapshot: **149 passed** (1.30s), Ruff check passed,
  Ruff format check passed for all six files, and `git diff --check` passed.
- An independent exhaustive script checked **1,296** no-history snapshot
  state/revision combinations (all six states, revisions 0 through 5, both
  snapshots) against the specified reachable states and legal transitions;
  accepted/rejected results all matched. This is additional offline script
  evidence, not an added pytest test count.
- These results cover local offline tests only. They are not GitHub Actions
  results, real Terraform Plan generation, authenticated approval evidence,
  persistent journal evidence, or real AWS/State compatibility.

## Remaining trust boundaries

All successful result objects remain `authorized=False`. Claimed Ed25519
signature bytes are only shape-checked; there is no authenticated issuer/key
registry, cryptographic signature verification, canonical signed-payload
contract or revocation policy. Caller-provided clocks are not authenticated.
No new signer or approval authority was created by this review.

Journal history can detect corruption and visible ID collisions in supplied
data. It cannot prove durable atomic reservation, distributed CAS, complete
global ID inventories, immutable storage, unseen rollback resistance or a
real execution result. Restart does not permit automatic retry; uncertain
execution must remain UNKNOWN/HOLD.

The Plan validator compares supplied source and producer claims with supplied
expectations and actual supplied Plan bytes. It does not authenticate the Git
origin/reviewer, freeze a checkout, prove official CLI/Provider provenance,
read real State, or prove that Terraform generated the Plan. Distinct supplied
Plan/Apply approval IDs are not yet bound to the actual complete approval
claims. Those authenticated composition and runtime gates remain HOLD
requirements for a separately reviewed implementation.
