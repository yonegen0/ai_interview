# PR #45 follow-up independent review — 2026-10-25 JST

**OFFLINE ONLY / NON-AUTHORIZING / Draft HOLD.** Issue #39 remains OPEN.
Formal execution remains Terraform 1.14.9. No AWS/STS/OIDC, remote State,
formal Plan/Apply, deployment, paid inference or protection changes occurred.

## Reviewed scope and independence

A separate review agent reviewed immutable change
`184ebab29fcde3374c5e6620b6bba72c5c1a1099..54980389815f5b755d3f72a847caa488b1a211e6`
in its own detached worktree. It did not implement those earlier five fixes.
The review covered both candidate helpers, both test modules, the HOLD document
and the original independent review report. PR #46 files were not edited.

The prior fixes correctly reject deferred action invocations, compare change
identities with both value inventories, prevent structural metadata from being
re-enabled inside attribute masks, reject static linked root ancestors, and pin
the final marker directory before creating a leaf. The review found one further
P2 affecting the remaining ancestor race, described below. This review and its
new correction do not authenticate the supplied evidence or authorize execution.
The correction itself subsequently received a separate review, recorded below;
that review does not authorize operational use.

## P2: ancestor replacement redirects local ledger writes

Affected functions in `backend/skills/p4/candidate_offline_controller.py`:
`exclusive_marker`, `private_subdirectory` and the path-based directory fsync
helper. `O_NOFOLLOW` on an absolute directory path protects only its final
component. An earlier static `linked_component` check cannot prevent a later
ancestor rename and symlink substitution.

Two deterministic Linux regressions failed against the original reviewed HEAD:

| Injection | Before correction | After correction |
| --- | --- | --- |
| Replace an ancestor immediately before the marker directory open | Marker was created in a different private directory | Symlink traversal raises before any redirected write |
| Replace an ancestor immediately before child directory creation | Child was created in the redirected private directory, even though later validation failed | mkdir uses the already pinned parent fd; no redirected child exists |

Both adversarial destinations are owned by the current UID and mode 0700, so
the existing final `fstat` ownership/permissions check did not detect redirection.
The regressions assert absence of redirected entries even if an exception occurs;
raising after an unsafe write is not treated as a successful defense.

Correction: `open_directory_without_links` starts at the filesystem root and
opens every component relative to the preceding directory fd with
`O_DIRECTORY | O_NOFOLLOW`. Marker creation and directory syncing use this
walk; child mkdir and parent fsync operate on a pinned fd. The final mutable
ledger directory is checked for owned/private permissions before creating an
entry. All descriptors from a failed walk are closed. Existing leaf-swap coverage
still proves that a rename after pinning writes to the originally pinned object,
without following the substituted symlink.

Five added tests cover the two ancestor races, file and directory fsync failure
(marker retained and reuse denied), and descriptor cleanup on an incomplete
directory walk. No existing security test was deleted or skipped. The existing
leaf-swap injection now waits for the final directory open because ancestor
opens are deliberately visible to the instrumentation.

## Remaining review findings and trust boundaries

| Concern | Review result / operational limit |
| --- | --- |
| Fail-closed / malformed input | Existing negative paths retained. Successful public review/reservation results remain `authorized=False`. Python exceptions also stop the operation. |
| Path traversal / static symlink / ancestor race | Existing path checks retained; newly reproduced ledger redirection cases corrected as above. |
| Directory fd / atomic marker creation | fd-relative `O_EXCL` marker creation and file/directory fsync retained. Separate approval and attempt writes are not a transaction. |
| Crash / fsync / partial write | Errors are propagated; created markers are retained and reject reuse. Physical durability across power loss is unproven. |
| Filesystem rollback / concurrency | Local owner deletion, replacement with another real private tree, or different hosts can defeat local one-use history. A pinned fd is not a distributed immutable authority. |
| Git / source TOCTOU | Local HEAD/tree/blob comparisons detect the tested byte changes. Git binary/config/object database, origin and signer are untrusted. Sequential file reads do not freeze an execution snapshot; Git ancestry races, hostile FIFOs and native Windows behavior remain unqualified. |
| Resource identity | Reviewed correction compares before/after identity against prior/planned inventories. Schema presence and no-op pair inventory checks remain active. This proves consistency of supplied JSON only. |
| Unknown / sensitive / deferred data | Unknown masks cannot regain structural metadata privileges after entering attributes. Sensitive flags do not imply drift. Deferred actions and malformed masks are rejected. |
| Terraform JSON compatibility | Major-1 show JSON and raw v4 State stay separate. Candidate 1.16.7 official Go serialization confirms deferred-action and identity fields. No real State upgrader compatibility is established. |
| Exceptions / retries / old namespace | The local contract propagates errors and does not start/retry a runtime. Old formal 1.14.9 contracts and namespaces remain separate. |
| Unauthenticated evidence / future controller | No supplied hashes, local marker, synthetic JSON or successful test can serve as execution authority. Authenticated provenance, signed approvals, externally anchored journal and real Plan origin remain HOLD prerequisites. |

## Verification

Linux WSL, Python 3.14.9, pytest 9.1.1, Ruff 0.16.7; locked dependencies were
not changed. Tests ran through an existing Linux virtualenv inside `unshare -n`.
Before correction, the two new ancestor regressions reported **2 failed**.
After correction, the two helper/test modules reported **69 passed** before the
additional three durability/descriptor tests were added. The final expanded
ten-file candidate/compatibility/legacy-controller/toolchain selection reported
**419 passed in 40.20s**, with no skipped or deselected tests. This includes
`test_candidate_bootstrap_preflight`, `test_candidate_offline_controller`,
`test_candidate_state_json_contract`, `test_candidate_state_snapshot_review`,
`test_toolchain_compatibility`, `test_bootstrap_maintenance`,
`test_bootstrap_recovered_apply`, `test_cloud_toolchain`,
`test_ci_toolchain_contract` and `test_toolchain_migration`.

Local Ruff check and format check over `skills/p4 tests/unit`: **PASS**, 168
files formatted. `git diff --check`: **PASS**. No Terraform CLI qualification
was repeated for this Python-only correction; the original report's prior
network-isolated CLI results remain historical evidence, not a new run or
authenticated signer proof. GitHub CI is checked by the integrating agent on the
new pushed HEAD; no old-head CI is claimed here as new-head validation.

Official sources consulted for this review:

- [Python 3.14 os fd-relative operations](https://docs.python.org/3.14/library/os.html)
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format)
- [Terraform 1.16.7 Plan serialization](https://github.com/hashicorp/terraform/blob/v1.16.7/internal/command/jsonplan/plan.go)
- [Terraform 1.16.7 planned resource identity/schema](https://github.com/hashicorp/terraform/blob/v1.16.7/internal/command/jsonplan/resource.go)

PR #43/#45 remain Draft/HOLD. A production candidate controller, authenticated
source and approvals, durable atomic journal, actual Plan producer/binary binding,
real State/API Gateway/SNS compatibility and independent operational approval
remain outstanding. This correction cannot lift those restrictions.

## Independent follow-up review of the ancestor-race correction

A second review agent, different from the author of this correction, reviewed
the complete four-file change: the controller, its regression tests, the HOLD
document and this report. This review inspected the actual working diff on
`54980389815f5b755d3f72a847caa488b1a211e6`; the reviewer changed only this report.
It covered root-to-leaf fd-relative traversal, `O_DIRECTORY | O_NOFOLLOW`,
private-directory ownership/mode checks, fd-relative mkdir and marker creation,
ancestor/leaf rename injection, file and directory fsync errors, descriptor
closure on failed traversal, and preservation of strict error propagation and
create-only marker reuse rejection.

The race tests deliberately accept an operation error only when no redirected
entry was created; this preserves the security property. The existing final
directory race still checks a successful write to the originally pinned object.
The fsync tests require the injected error to propagate and the marker to remain
consumed. The failed-walk test tracks all opened descriptors and requires none
to remain open. Updating the prior race injection to recognize the final
component open is consistent with the new ancestor traversal and does not
remove or skip the original regression.

Independent Linux WSL execution in `unshare -n` produced:

- Both affected candidate helper/test modules: **72 passed in 5.32s**.
- The ten-module selection listed above: **419 passed in 47.03s**.
- Ruff check over `skills/p4 tests/unit`: **PASS**; Ruff format check:
  **168 files already formatted**; `git diff --check`: **PASS**.

No concrete unresolved P1/P2 was identified in this correction's reviewed
scope. The reviewer also checked the documented fd-relative semantics against
[Python 3.14 os operations](https://docs.python.org/3.14/library/os.html) and
the [Linux open/openat manual](https://man7.org/linux/man-pages/man2/open.2.html).

This closes the separate source-review requirement for the ancestor-symlink
correction only. Same-owner deletion, replacement with a different real tree,
mount manipulation, cross-host one-use guarantees, physical storage durability,
authenticated source/approval evidence and source-to-execution freezing remain
outside the demonstrated guarantee. These are local offline tests, not fresh
GitHub CI or actual Terraform/AWS execution evidence. Draft/HOLD remains.
