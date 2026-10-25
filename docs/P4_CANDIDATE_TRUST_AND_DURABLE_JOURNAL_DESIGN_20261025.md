# Issue #39: candidate trust and durable journal design

2026-10-25 JST. **OFFLINE_ONLY / NON_AUTHORIZING / Draft / HOLD.**
This design does not release PR #43, #45 or #46, change the formal Terraform
1.14.9 baseline, approve any AWS access, or introduce an executable controller.

## Implemented increment and evidence boundary

`backend/skills/p4/candidate_journal_model.py` adds an in-memory repository model.
It imports the candidate journal contract, keeps both one-use ID indexes and
complete event histories behind one Python lock, compares the complete expected
head for CAS, and deep-copies inputs and returned views. Synthetic response loss
can occur immediately before or after the atomic commit point; both raise the
same `ModelIndeterminateError` and require HOLD. No method grants a retry.

The tests model two clients sharing **one repository instance**, competing for
approval IDs, attempt IDs and the same CAS head. They also cover missing fields,
rewritten heads, gaps, backward transitions, terminal states, retained ID indexes,
input/output mutation and response loss. Two independent instances intentionally
accept the same synthetic IDs, demonstrating the absence of distributed proof.

Every successful result is `authorized=False`, `retry_permitted=False`,
`persistence_verified=False`, `global_uniqueness_proven=False`. The model has no
AWS SDK, filesystem storage, external calls, execution callbacks, TTL, deletion,
production adapter or authentication. A caller could invoke the repository again
after an injected pre-commit failure; the model does not enforce a caller's HOLD
across processes. A future controller needs its own durable uncertainty record and
must stop even when readback finds no entry. Tests are storage-law examples, not
authority to perform that retry.

## A. Authenticated and frozen source

The proposed execution manifest must bind the repository's immutable identity,
permitted origin, exact reviewed commit and tree, review decision and policy
version, and an inventory of all Terraform source bytes. Resolve the expected
origin and review decision through an independently authenticated GitHub connection,
then validate the commit signer against a separately enrolled trust policy.
Record verification time and reasons. GitHub documents a commit verification
object, but a `verified` flag alone is not this project's review/adoption policy.
[GitHub commit verification](https://docs.github.com/en/rest/commits/commits).

Do not accept a local `origin` URL, local object hash, caller-supplied verification
flag, or a new signer key found in the commit as the trust root. A valid commit
signature does not authorize running it. Missing signatures or review evidence
require HOLD unless a separately approved source policy explicitly resolves them.

Create a sterile snapshot from the authenticated tree; inventory root modules,
local modules, lock files, generated files and non-HCL inputs before qualification.
Reject untracked overrides, symlinks, path traversal and Git environment overrides.
Constrain external module sources and their immutable content separately: Provider
locks do not lock remote module source bytes. Freeze the snapshot against changes
by the execution identity. Re-hashing a mutable checkout immediately before running
it does not close the time-of-check/time-of-use gap. The existing PR #45 local Git
check remains a useful offline consistency check, not authenticated frozen source.

## B. Signed approval envelope and trust enrollment

Keep v3 claim validation non-authorizing. A future authenticated envelope needs a
new explicit schema/kind or versioned policy, with domain-separated signed bytes.
Proposed domain: `ai_interview:p4:candidate:approval:<schema>`. The signed payload
includes issuer, key ID, algorithm, policy/trust-store revision, namespace,
operation, source commit/tree/inventory, CLI version/platform/binary digest,
Provider version and full inventory digest, configuration/lock digest, State
identity, Plan digest, approval/attempt IDs, issuance and expiry, plus the
deployment/account/region/resource scope and execution/cost limits. Exclude only
the signature bytes themselves. Reject unknown fields and duplicate JSON keys.

Choose and test one canonicalization contract across producer and verifier.
[RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785) specifies a deterministic
JSON representation; Python `json.dumps(sort_keys=True)` is not by itself a JCS
implementation. The proposed schema should avoid floats and ambiguous number or
Unicode representations. This change implements neither canonicalization nor
signature verification. There is no cryptographic verification of existing v3
`signature_claim` objects.

[RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) describes Ed25519, and a maintained
library exposes public-key verification, for example
[cryptography Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
A later implementation must select and lock a reviewed library, use official
test vectors and malformed-signature tests, and verify the exact canonical bytes.
No crypto dependency or key is added here.

Enroll issuer/public-key mappings outside caller input through explicit owner
approval; bind full public-key fingerprints, allowed operations, namespace and
validity. Reject unknown, revoked, substituted or out-of-scope keys. Check trusted
time, bounded lifetime and expiry again before reservation/start; failure to
establish a clock or current revocation policy requires HOLD. Do not silently add
clock-skew tolerance that extends validity.

Plan and Apply require different approval IDs and independently signed payloads.
Both maintenance-plan and recovery-plan bind `plan_sha256=null` before producing
a Plan; their Apply approvals bind the produced bytes. Enforce exact operation
pairs and separate attempts, and bind each actual verified approval claim to its
ID and payload digest in the producer receipt and journal. PR #46's comparison
of two different supplied IDs does not establish this linkage. An old namespace,
schema, consumed approval or changed target must never be converted into a new
approval automatically.

## C. Durable journal and atomic one-use reservation

Target one authoritative account/Region and one linearizable storage domain per
candidate namespace. All hosts must use that same authority. Do not substitute
per-host marker files, separate repository instances, eventual replicas or a
last-writer-wins multi-Region arrangement for atomic one-use enforcement.

Proposed durable transaction layout (not implemented or provisioned):

| Record | Required condition / invariant |
| --- | --- |
| Approval tombstone | Namespace + approval ID does not exist; then permanently bind attempt and payload digest |
| Attempt tombstone | Namespace + attempt ID does not exist; bind approval and target digest |
| Attempt head | Reserve NEW/0 and RESERVED/1 with their complete immutable binding |
| Append-only events | Event key does not exist; store ordered event and predecessor digest |

Reserve both IDs, head and initial events in one all-or-nothing transaction.
For each later transition, condition the existing head on the exact prior
revision/state/binding/digest, append the next event once, and update the head in
one transaction. Use conditions on the modified item rather than a separate
ConditionCheck and Update of the same item. DynamoDB documents atomic
`TransactWriteItems` within an account/Region and a **10-minute** request-token
window. That window cannot serve as permanent replay prevention.
[DynamoDB TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html).

Do not TTL or delete one-use tombstones when an approval expires or a run ends.
Separate privacy retention for encrypted event details from permanent digest/ID
evidence. IDs and payload digests must not contain credentials or full private
State/Plan bytes. A production adapter, IAM enforcement, encryption, storage
retention and access/readback verification remain separate approval work.

The contract is NEW/0 → RESERVED/1 → STARTED/2 → COMPLETED/FAILED/UNKNOWN/3;
RESERVED/1 can also become UNKNOWN/2 after an interrupted start. Terminals have
no outgoing transition. Reservation/start failures, timeout, response loss,
conflict, missing events, partial write, unexpected revision, stale anchor or
readback uncertainty require UNKNOWN/HOLD; never infer that Terraform did not
run from an absent completion event. Reconcile under separately approved recovery
instead of automatic execution retry. SDK retry policy must not create an
unbounded retry path around this rule.

Rollback resistance needs a separately protected monotonic high-water mark or
externally witnessed checkpoint tied to the journal generation and history root.
Hash chaining and a newer-looking revision cannot detect restoration of a whole
old database when every local anchor is restored with it. Reads and CAS must bind
the current checkpoint; missing/unavailable/mismatched checkpoint requires HOLD.
Restore, truncation, checkpoint rotation and disaster recovery need explicit
review and approval. The model intentionally does not claim this property.

## D. Source-to-Plan producer receipt and execution binding

Only a future trusted producer may issue a signed receipt after running an
approved Plan operation against the frozen source/toolchain. Receipt content must
bind source and toolchain manifests, provider packages and loaded executable
hashes, explicit arguments, workspace/configuration digest, approved target,
State lineage/serial/VersionId/raw-bytes digest before and after Plan, actual
process outcome, Plan bytes digest, Plan approval payload/ID, attempt and producer
identity. The consumer must authenticate both producer and receipt policy; the
caller cannot appoint an arbitrary `producer_id` as trusted.

At Apply, authenticate an independent Apply approval over that exact receipt and
Plan bytes, compare target/current State against its allowed preconditions, and
reserve its one-use IDs. Transfer the protected exact Plan artifact to the
executor, pin it against replacement, then verify the bytes the executor actually
opens. Reject a regenerated Plan, a matching caller-supplied hash with no producer
receipt, mutable path replacement, crossed maintenance/recovery operation, changed
source/locks/toolchain or stale State. Authentication and reservation must precede
any privileged execution.

HashiCorp documents saved Plan files as containing the intended actions and full
configuration, input values and potentially cleartext sensitive values. Keep the
artifact and raw State private and encrypted; public summaries contain only
approved redacted evidence. This document does not run Plan or Apply.
[Terraform Plan reference](https://developer.hashicorp.com/terraform/cli/commands/plan).

## E. CLI and Provider authenticity

For each exact CLI version/platform, obtain archive, checksums and detached
signature from the official release source; verify the checksum signature under
an independently trusted current HashiCorp public key, then verify the archive
checksum. Also record the extracted executable digest and protect the executable
that will actually run. The signature does not automatically authenticate an
arbitrary same-directory binary or prevent later replacement.
[HashiCorp archive verification](https://developer.hashicorp.com/terraform/tutorials/cli/verify-archive).

Provider policy must bind registry source, version, platform, reviewed lock file,
package hash, signer fingerprint/trust classification and the extracted executable
inventory. Terraform's lock records package checksums with trust-on-first-use
behavior, and registry installation authenticates signatures according to signer
classification; manually installed plugins need separate verification. A lock
digest or executable version string alone proves neither signer trust nor which
binary was loaded. Reject unreviewed mirrors, development overrides and altered
plugin caches. Preserve six-scope baseline lock differences until authorized.
[Dependency locks](https://developer.hashicorp.com/terraform/language/files/dependency-lock),
[Provider signatures](https://developer.hashicorp.com/terraform/cli/plugins/signing).

Prior checksum matches remain historical consistency evidence. This work has not
performed PGP signature verification, established a current trusted signer key,
qualified actual loaded Provider executables, or completed real State/AWS
compatibility. Candidate 1.16.7/Provider 6.70.0 adoption remains separate from the
formal 1.14.9 runtime and cannot be inferred from Mock or CI success.

## Verification and remaining gates

Local Python 3.14.9, locked existing dependencies: new model tests **29 passed**;
with the three repaired PR #46 contract modules **178 passed**. No tests are
deleted/skipped. Ruff check and format check apply to the two new Python files.
Independent review and genuine new-HEAD CI must be recorded separately by the
integrating reviewer; these local counts are not CI evidence.

Before any future executable controller, require all of: authenticated source and
review policy; reviewed immutable snapshot; enrolled/revocable approval and
producer trust; canonical signed-byte verification and actual claim-to-ID linkage;
durable dual-ID CAS adapter with uncertainty handling; independent rollback
checkpoint; official signer/CLI/Provider evidence; authorized real State/AWS
compatibility proof; fresh operation-specific approvals; independent security
review and explicit HOLD release. The present Draft remains non-authorizing while
each missing property is implemented and tested within its permission boundary.

## Independent review of this offline increment

A different review agent inspected the new repository model, all accompanying
tests, and this complete A-E design. The reviewer did not implement or modify
the Python files. Reviewed properties included atomic dual-ID reservation within
one shared mock instance, complete-snapshot CAS, binding and transition checks,
input/output copy isolation, conflict and partial-input rejection without
partial ID consumption, competing thread clients, terminal states, and synthetic
response loss on either side of the model commit point.

Independent execution on Linux WSL in `unshare -n` reported **178 passed in
9.59s**: 29 model tests plus 149 repaired PR #46 contract tests. Ruff check and
format check passed for both new Python files; `git diff --check` passed.
No network or Terraform process was used by the model. The concurrent tests use
threads sharing one Python object, not separate hosts or an actual database.

No concrete unresolved P1/P2 was identified within this explicitly mock-only
increment. The successful result objects remain non-authorizing and do not
claim persistence, global uniqueness or retry permission. The model's
all-or-nothing in-memory update is a stated abstraction that a real storage
adapter must independently establish; it is not fault-tolerant persistence.
Pre-commit response loss does not itself permanently poison an absent mock
record, and the API can be called again. The documented requirement for a
future controller to preserve UNKNOWN/HOLD even after absent readback therefore
remains necessary and unimplemented.

The reviewer checked the cited official specifications for the design's
security-relevant distinctions: GitHub signature verification versus adoption
policy; RFC 8032 Ed25519 and RFC 8785 canonical bytes versus ordinary JSON
serialization; DynamoDB atomic writes, same-item restrictions and the bounded
10-minute request-token window; saved Plan confidentiality; and HashiCorp archive
signatures, checksums, dependency-lock trust-on-first-use and Provider signing.
These are design references, not evidence that signatures, durable transactions,
authenticated source, or real Provider/State compatibility were exercised.

The independent source review is complete for these three files. Genuine CI on
the final pushed HEAD is recorded separately by the integrating agent. Draft/HOLD
and all operational authenticity and approval gates above remain in force.
