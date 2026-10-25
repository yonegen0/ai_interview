# Issue #39 / PR #45 — Codex independent offline review (2026-10-25 JST)

## 1. Conclusion and scope

**Offline review/verification completed; operational adoption remains HOLD.**
Original independent review target: `184ebab29fcde3374c5e6620b6bba72c5c1a1099`.
Main observed at start: `aa5952930160c7a6bb91765bd0bfd542500becde`.
This review read all eight added PR files and the related compatibility,
maintenance and recovery contracts/controllers. It found five reproducible P2
issues in candidate-only helpers. Regression tests failed before the respective
fixes. The changes below are Codex's own fixes and self-review, separate from the
independent review of the original ChatGPT implementation. No second independent
review of these fixes is claimed.

No concrete P0/P1 in the reviewed non-executing path was established. Missing
operational trust and immutable-journal guarantees remain adoption blockers;
offline success does not satisfy them. No old failed CI issue was reclassified
as a new defect, and no existing test was removed or skipped to hide a failure.

AWS authentication/STS/API, remote State, formal Plan/Apply, deployment, paid AI,
readiness/Ruleset changes and merge: **zero operations** in this review.
PR #43/#45 remain Draft/HOLD and Issue #39 remains OPEN.

## 2. GitHub and original CI

Branch: `chatgpt/issue39-candidate-preflight-20261025`; original HEAD as above.
PR #43 observed HEAD: `789dfa2d907f430e64412f7fd31b2a4978910bfb`, OPEN/Draft.
PR #45 observed OPEN/Draft, unmerged. Issue #39 observed OPEN.
Existing source-directory edits were preserved; an isolated detached worktree
was created, then a local `codex/` branch is used for a normal commit/push to the
existing PR branch. No force push, branch deletion or main change is authorized.

The GitHub connector independently returned these completed SUCCESS runs for
the original HEAD; none was rerun:

| Workflow | Run ID |
| --- | --- |
| Backend | 40180078094 |
| Frontend | 40180078048 |
| Infrastructure/package | 40180078046 |
| Candidate qualification | 40180078044 |

New-HEAD workflow/job results are recorded in the PR/Issue follow-up after push;
this pre-push report does not claim those runs have already passed.

## 3. Eight-file independent review

Paths below are relative to the repository. Original line numbers refer to
`184ebab`; the fixes/tests are visible in the follow-up commit.

| Original file | Independent result | Fix/tests and remaining limit |
| --- | --- | --- |
| `backend/skills/p4/candidate_bootstrap_preflight.py` | No additional concrete P0/P1/P2 established. Cross-operation saved Plan rejection, old namespace/approval/CLI/platform, exact fields and NEW journal checks reviewed. | Unchanged. Regex is not an HCL parser; supplied hashes, version JSON, approvals, journal and Plan descriptors are not authenticated. Always `authorized=False`. |
| `backend/tests/unit/test_candidate_bootstrap_preflight.py` | Synthetic positive/negative tests reviewed, including maintenance/recovery crossing and old-contract preservation. | Unchanged and executed. Synthetic binary/locks deliberately cannot prove official provenance. |
| `backend/tests/unit/test_candidate_state_json_contract.py` | Synthetic API Gateway identity, SNS default and provider-schema regressions reviewed. | Unchanged and executed. Its generic compatibility fixture is not an actual CLI Plan; the stricter snapshot fixture adds schema metadata. |
| `docs/P4_CANDIDATE_BOOTSTRAP_PREFLIGHT_HOLD_20261025.md` | HOLD boundaries and absence of an executable candidate path reviewed. | Supplemented with this review. Local marker one-use claims remain limited to retained files in a trusted local directory. |
| `backend/skills/p4/candidate_offline_controller.py` | P2-4 and P2-5 below. Commit/tree/blob checks, full inventory, GIT environment isolation, SHA-1-only handling and freshness reviewed. | Reject static linked ancestors; pin the marker directory before leaf creation. Source/Plan atomicity, ancestor races, owner rollback and distributed authority remain unproven. |
| `backend/tests/unit/test_candidate_offline_controller.py` | Existing tamper/path/expiry/crash tests reviewed; ancestor and directory-swap regressions were missing. | Three new Linux regressions. Existing tests retained. A separate two-process/fault harness also ran. |
| `backend/skills/p4/candidate_state_snapshot_review.py` | P2-1, P2-2 and P2-3 below. Raw-v4 identity/digest/strict decoding, format version, sensitivity and no-op delegation reviewed. | Reject deferred actions, bind change identities to prior/planned values and prevent metadata parsing inside attribute masks. Real State/upgraders remain unproven. |
| `backend/tests/unit/test_candidate_state_snapshot_review.py` | Missing regressions for those three input-validation gaps. | Added deferred-action, baseline/candidate identity, unchanged-identity and nested-mask tests. Existing rejection tests retained. |

Related files inspected: `toolchain_compatibility.py`, its unit tests,
`bootstrap_maintenance.py`, `bootstrap_recovered_apply.py`, `maintenance_contract.py`
and `recovery_contract.py`. They were not modified. This is not a claim of a fresh
complete security audit of all historical operational controllers.

### P2-1 — Deferred action invocations ignored

- Original: `candidate_state_snapshot_review.py:87`.
- Cause: the unsupported-action list omitted `deferred_action_invocations`, a
  field in Terraform 1.16.7's actual JSON Plan implementation.
- Reproduction: add a nonempty deferred-action list to an otherwise accepted
  synthetic no-op; comparison still returned success. Malformed empty object,
  null and boolean were also ignored.
- Impact: an offline compatibility report could omit deferred work. There is
  no candidate Apply path and no resulting authorization.
- Fix: allow the field only when absent or exactly an empty list.
- Regression: four formerly failing cases in
  `test_deferred_action_invocations_cannot_hide_in_noop_plan` now pass.

### P2-2 — Change identities not bound to values

- Original: `candidate_state_snapshot_review.py:113`; delegated comparator
  compared attribute values but not `change.before_identity/after_identity`.
- Reproduction: keep both documents' prior/planned identity objects identical,
  then change, remove or substitute a change-row identity on either document.
  The original comparison accepted the inconsistent evidence.
- Impact: false offline no-op/identity assurance for providers with identity
  support, including the API Gateway compatibility review area.
- Fix: canonical comparison of change identities with each other and the
  matching prior/planned resource identities; validate non-null identity schema
  metadata. No identity is inferred from an unknown provider schema.
- Regression: eight negative cases plus an unchanged-identity positive test.

### P2-3 — Attribute masks could regain structural privileges

- Original: `candidate_state_snapshot_review.py:39`.
- Reproduction: proposed unknown values containing an attribute named
  `resources`, then nested `address: "malformed-unknown"`, were accepted.
- Cause: key names re-enabled metadata mode even after entering attribute values.
- Impact: malformed unknown evidence could pass the candidate supplemental gate.
- Fix: once in attribute-mask mode, recursive descent cannot re-enable metadata.
- Regression: `test_attribute_names_cannot_reenter_structural_unknown_metadata`.

### P2-4 — Symlink ancestors accepted

- Original: `candidate_offline_controller.py:122` and `:334`.
- Reproduction: pass `/private/alias/checkout` or `/private/alias/ledger`, where
  `alias` is a symlink and the final directory itself is real/private.
- Cause: only the final path component was checked before resolution or lstat.
- Impact: bypassed the helpers' static real-directory/source-path requirement.
- Fix: inspect the path and every lexical ancestor for symlink/junction.
- Regression: both Git and ledger ancestor cases now reject. This is a static
  check and does not claim to freeze all ancestors against later replacement.

### P2-5 — Marker write could escape through a swapped parent

- Original: `candidate_offline_controller.py:365-389`.
- Reproduction: replace the validated approvals directory with a symlink before
  leaf creation. The old helper wrote a marker in the redirected directory and
  only then failed directory fsync with `NotADirectoryError`.
- Cause: `O_NOFOLLOW` on a leaf does not protect its parent; syncing reopened the
  directory by pathname after writing.
- Impact: unintended local write before fail-closed return; no AWS execution.
- Fix: open the marker directory with `O_DIRECTORY|O_NOFOLLOW`, verify its owner
  and mode, create the leaf relative to that fd, and fsync that same fd.
- Regression: deterministic replacement before/after parent-open plus the
  external race harness; the redirected directory now receives no marker.
- Remaining: this pins the final parent during one marker write. It is not a
  whole-ancestry race proof or durable approval authority.

## 4. Real Terraform / Provider verification

Public downloads were obtained from HashiCorp over HTTPS and matched its
SHA256SUMS. No pre-existing Terraform/provider cache was trusted. Detached PGP
signatures and signer trust were **not** verified; that distinction remains
explicit rather than calling the manifests independently signed/attested.

| Official linux_amd64 ZIP | SHA-256 |
| --- | --- |
| Terraform 1.16.7 | `5454efcf7fc87f0c2113111b9a5c7182f0ca1c6f0f23a1e110a50770a8fe473b` |
| Terraform 1.17.0 | `c168cab7c637a8769fdb90089ddd19de701bc6ff8aca64dc2e2185fe46f59f67` |
| AWS Provider 6.70.0 | `58acc041b080778ded75320e241ebcf6cf2ed145bede644b86a4784ce46086c6` |

Extracted Terraform binary SHA-256:

- 1.16.7: `54533008a91f4aa992bb530963f6a902f67f4cf75245c014cdf57df4afb8d2ec`
- 1.17.0: `664b66cc0bcd7ed28fd27569719ccaa8a40c230b8be45060ce4d65e2852e1bcc`

Both actual `version -json` outputs reported their exact version and
`platform=linux_amd64`. CLI binaries were invoked by their absolute Linux paths.

Provider windows_amd64 ZIP also matched the official checksum:
`2d8c016b3809ab32f536b01bf2c98fcbdeb066b7b7e50f756ff6ff1e0b0539c7`.
It was hashed, not executed. The six candidate locks were byte-identical, SHA-256
`bfb4d43aa58cfdc129f3dec7407a17e09d1b1fd499541c29954981ee170d3ed9`.
All 16 `zh:` values in each lock matched the complete official package checksum
set. Both actual Linux/Windows ZIP content hashes matched their `h1:` entries:

- Linux: `h1:HCr4MYgxlkFBOAeWKOoktNNzZaQX8ZZY4YTxmL/1V/Y=`
- Windows: `h1:qyaviwNzelpKOn0sf1G+LYSdLf0BvGjhvBANYLe9UCw=`

### Six-scope CLI results and source distinction

PR #45's actual Terraform source still requires CLI **1.14.9**, provider
constraint `~> 6.0` and the existing 6.64.0/6.65.0 locks. For **all six scopes**,
both candidate CLIs rejected backend-disabled readonly init against that source
with the legacy required-version condition. This is expected fail-closed
behavior, not proof that PR #45 has adopted the candidate configuration.

For positive candidate qualification, a disposable copy of PR #45's tracked
configuration received only six requirement files and six locks from the fixed
PR #43 SHA above. The requirement-file diff was exactly the CLI/provider pin
change. For 1.17.0 comparison, only its disposable CLI requirement was changed.
No live checkout or tracked lock was modified.

| Scope | CLI 1.16.7 | CLI 1.17.0 comparison |
| --- | --- | --- |
| bootstrap | fmt/init/validate PASS | fmt/init/validate PASS |
| environments/dev | fmt/init/validate PASS | fmt/init/validate PASS |
| environments/test | fmt/init/validate PASS | fmt/init/validate PASS |
| environments/web | fmt/init/validate PASS | fmt/init/validate PASS |
| modules/frontend | fmt/init/validate PASS | fmt/init/validate PASS |
| modules/service | fmt/init/validate PASS | fmt/init/validate PASS |

Commands: `fmt -check -no-color`,
`init -backend=false -input=false -lockfile=readonly -no-color`, and
`validate -json`. Candidate lock bytes remained unchanged after every scope.
Actual corrupt-checksum init was separately rejected (exit 1), using the verified
local provider ZIP and no network. No Plan/Apply command or Terraform test run
was used in this review.

All Terraform processes ran inside Linux `unshare -n`. The parent downloaded
only public packages; child processes used an explicit environment with an
empty private HOME/credential files, explicit CLI config, checkpoint disabled,
and a filesystem provider mirror with no direct installer. No inherited TF CLI
args, AWS credentials/profile/endpoints or provider cache was passed. Local
modules were used. Network-blocked validation is not AWS IAM verification.

Both CLIs returned provider schema `format_version=1.0`, 1,742 resource schemas,
API Gateway REST API schema version 0 and SNS topic schema version 0. This checks
schema serialization/availability, not remote State upgrades or defaults.

Both real CLIs also ran `show -json` on a newly generated **synthetic local v4
State** containing built-in `terraform_data`, inside a separate backend-disabled
directory. Both emitted `schema_version: 0` and JSON State `format_version=1.0`.
Target-version HashiCorp source explicitly emits resource schema_version without
omitempty for both State and planned values. Therefore the existing mandatory
nonnegative schema-version check was retained. No real AWS State was read and
no Plan was generated to obtain this result.

## 5. Git and local filesystem fault results

A network-isolated Linux shared clone of the local object database was checked
out at the fixed original PR #45 SHA with autocrlf disabled. The helper verified
57 tracked Terraform files, tree `80d2b41e2a8030c9d149a39cff132ca3004e2acd`,
inventory digest `01d92273500773aeea2855ab5025945cb15864d16eafd6e86b362e289bb0d985`.
Changing an actual copied tracked file caused `CandidateGitBlobMismatch`.
No Git origin/signature authentication is inferred from the local clone.

Synthetic attack repositories also rejected extra HCL JSON, override, auto tfvars,
ignored HCL, and replace-ref substitution. A real SHA-256 Git repository was
rejected as unsupported. Existing negative tests cover missing/wrong HEAD,
missing scope/file, path traversal and final-component symlinks.

The following limitations were **observed**, not declared safe:

- Staging different bytes while restoring the checkout to the reviewed commit
  still passes. The helper inspects commit/checkout bytes, not index cleanliness.
- The local executable/config/object database, SHA-1 collision assumptions,
  reviewed-commit origin and signatures are not independently authenticated.
- Reading files sequentially is not an immutable execution snapshot. Concurrent
  source changes, ancestor replacement and source-to-Plan binding remain HOLD.
- FIFO blocking/hostile filesystem availability, Windows-native Git-helper
  behavior and a full adversarial ancestry race proof were not qualified.

The Linux journal harness used two real processes plus injected faults in fresh
temporary directories only:

| Case | Observed result |
| --- | --- |
| Same approval, simultaneous processes | Exactly one reservation; other FileExistsError |
| Different approvals, same attempt | Exactly one reservation; competing approval stays consumed |
| Exit after partial marker write | Retry refused; partial marker retained |
| File fsync failure | Error returned, marker retained, retry refused |
| Directory fsync failure | Error returned, marker retained, retry refused |
| Process exit immediately after approval marker | Retry refused |
| Consumed marker restoration | Retry refused while marker exists |
| Unsafe root permissions | Rejected |
| Parent symlink race | Before fix: redirected write then error; after fix: error without redirected marker |
| Owner deletes both markers | Re-reservation succeeds offline only — LIMITATION |
| Owner replaces root with new private directory | Re-reservation succeeds offline only — LIMITATION |
| Other hosts / rollback / actual power loss | No distributed or physical durability proof — UNKNOWN |

None of these operations starts AWS work or makes `authorized=True`. Holding
directory fds does not make mutable local files an immutable one-use authority.

## 6. Verification, remaining work and next concrete steps

Local tools: WSL Ubuntu Linux x86_64, uv 0.13.5, locked Python 3.14.9,
pytest 9.1.1, Ruff 0.16.7. Both Windows and Linux dependency setup used
`uv sync --locked`; tracked dependency versions/locks were unchanged.
The final network-blocked Linux selection across ten candidate, compatibility,
legacy maintenance/recovered-apply and toolchain test files: **414 passed**.
Ruff check/format passed on all four changed Python files; `git diff --check`
passed. Original failing regressions and the CLI/fault outputs were retained
outside the repository under the task's local evidence directory.

Reproduction test selection from `backend/`:

```text
uv run --locked pytest -q tests/unit/test_candidate_bootstrap_preflight.py tests/unit/test_candidate_offline_controller.py tests/unit/test_candidate_state_json_contract.py tests/unit/test_candidate_state_snapshot_review.py tests/unit/test_toolchain_compatibility.py tests/unit/test_bootstrap_maintenance.py tests/unit/test_bootstrap_recovered_apply.py tests/unit/test_cloud_toolchain.py tests/unit/test_ci_toolchain_contract.py tests/unit/test_toolchain_migration.py
uv run --locked ruff check skills/p4/candidate_offline_controller.py skills/p4/candidate_state_snapshot_review.py tests/unit/test_candidate_offline_controller.py tests/unit/test_candidate_state_snapshot_review.py
uv run --locked ruff format --check skills/p4/candidate_offline_controller.py skills/p4/candidate_state_snapshot_review.py tests/unit/test_candidate_offline_controller.py tests/unit/test_candidate_state_snapshot_review.py
```

Use Linux for the candidate filesystem helpers and their full test selection.
No claim is made that these commands alone enforce network isolation; this run
additionally used an empty environment and `unshare -n`.

Next work for ChatGPT/implementation:

1. Independently review the new helper/test diff before relying on its findings.
   Require the new identity/deferred/mask/linked-ancestor/directory-swap tests to
   remain green and every successful result to remain non-authorizing.
2. For a future candidate controller, design authenticated source/executable
   provenance, signed expiring approvals and an externally anchored atomic
   attempt authority. Keep it disconnected from existing execution controllers
   until separately reviewed; local marker deletion/rollback must never grant a
   real retry. No candidate execution path was implemented here.
3. Require an immutable complete source snapshot and saved Plan origin binding,
   full HCL parsing, controlled Git execution/config and all-ancestor filesystem
   handling. The current helpers are supplemental offline validators.

Codex-specific observed evidence in this run: actual Linux CLI/platform/checksum,
all-six-scope readonly init/validate, real provider schema, actual synthetic
show-json schema-version output, real local Git object/checkout comparisons and
multi-process/filesystem fault behavior. These are reusable local verification
facts, not exclusive capabilities or operational adoption approval.

Still unreviewed/unproven: a fresh independent review of Codex's fixes, production
controller design, authenticated approvals, distributed crash/rollback semantics,
real State VersionId/lineage/serial/hash, provider State upgraders, resource
identity/default migration and AWS readback/IAM. Actual AWS/State read,
formal Plan/Apply, operational adoption and HOLD release require fresh explicit
authorization for exact targets/SHA/operations. PR #43/#45 stay Draft/HOLD;
Issue #39 stays OPEN; formal CLI remains 1.14.9.

Official references:

- [Terraform 1.16.7 packages/checksums](https://releases.hashicorp.com/terraform/1.16.7/)
- [Terraform 1.17.0 packages/checksums](https://releases.hashicorp.com/terraform/1.17.0/)
- [AWS Provider 6.70.0 packages/checksums](https://releases.hashicorp.com/terraform-provider-aws/6.70.0/)
- [Dependency lock semantics](https://developer.hashicorp.com/terraform/language/files/dependency-lock)
- [JSON format](https://developer.hashicorp.com/terraform/internals/json-format)
- [1.16.7 Plan fields and identity serialization](https://github.com/hashicorp/terraform/blob/v1.16.7/internal/command/jsonplan/plan.go)
- [1.16.7 planned-resource schema version](https://github.com/hashicorp/terraform/blob/v1.16.7/internal/command/jsonplan/resource.go)
- [1.16.7 State resource schema version](https://github.com/hashicorp/terraform/blob/v1.16.7/internal/command/jsonstate/state.go)
- [init](https://developer.hashicorp.com/terraform/cli/commands/init) / [validate](https://developer.hashicorp.com/terraform/cli/commands/validate)
