# PR B: candidate version adoption — HOLD / DO NOT MERGE

This **unmerged Draft** proposes Terraform **1.16.7** and AWS Provider **6.70.0**.
It does not authorize adoption, AWS authentication/API/read, remote State,
formal Plan/Apply, readiness changes, deployment or paid inference.
The deployed/formal baseline remains 1.14.9 until a separately approved merge.
Issue #39 remains OPEN; public release remains NOT READY.

## Prepared candidate changes

- Six exact CLI/provider requirements and six **official CLI-generated** linux_amd64 /
  windows_amd64 lockfiles from the native Windows qualification/export described in
  [the operational compatibility assessment](P4_TOOLCHAIN_OPERATIONAL_COMPATIBILITY_20261025.md).
  No checksum was hand-written. Only these requirements/locks change in Terraform.
- The shared new-execution pin and all six setup-terraform workflow version pins
  change together. Action commit pins, AWS/OIDC permissions, readiness gates, normal
  additive lock guards and required checks are preserved.
- Tests retain strict rejection of baseline 1.14.9/other candidate 1.17.0 for proposed
  new execution. Historical maintenance/recovery pins and fixtures stay **1.14.9**.
- Formal execution explicitly requires `linux_amd64` (the existing Ubuntu workflows).
  Shared pre-authentication checks reject another/missing platform or unknown version
  JSON format. New dev saved Plan bindings, independent audit and test Closure receipts
  bind the platform/runtime; old or cross-platform bindings fail closed. Windows
  candidate qualification remains separate and does not authorize Windows execution.
- The candidate matrix reads immutable pre-upgrade configuration at
  `7ec3595aa02c5315f6d7600282b428d294d3d771` in a second credential-free checkout,
  using current candidate validator code. This preserves genuine old -> new migration
  testing instead of changing its accepted baseline. Before provider initialization,
  the matrix also compares the actual PR B checkout against that immutable source:
  file inventory and every other tracked Terraform byte must remain unchanged.
  This immutable comparison runs only for the same-repository PR B branch
  `codex/issue39-upgrade-b-hold-20261025`; it does not run on main pushes or ordinary
  development PRs. Its skipped jobs on other branches are intentional. The normal
  `terraform` required check separately validates the actual checkout, additive lock
  integrity and mocks. Backend version-contract tests retain the exact reviewed
  toolchain/workflow requirements. The five required check names and Ruleset are
  unchanged. A future toolchain migration needs its own reviewed comparison scope.

To repeat migration qualification locally, pass a separate checkout of that legacy
source as `--repository`; the migration runner intentionally rejects already-upgraded
configuration as its baseline. All generated work must remain disposable and offline.

## Merge blockers — passing CI alone cannot release HOLD

1. **Future bootstrap maintenance/recovery execution remains incomplete.** Current
   readers/executors retain the old source/CLI contracts. Preserve their original
   checkout, toolchain, approvals and receipts. They must not be run against the new
   bootstrap HCL or silently allowed to accept a candidate version. A separate future
   operation/approval namespace and reviewed execution path are still required.
   Legacy maintenance now checks CLI 1.14.9 and the native amd64 platform without
   credentials, in an empty temporary directory, before authentication or attempt
   consumption. It also rejects candidate/missing HCL requirements even with an old
   Provider lock. Recovered Apply checks the approved absolute binary before its
   reader or attempt journal. Existing later version/hash checks remain in place.
   Read-only recovery/inspection do not execute Terraform; their existing immutable
   configuration/approval checks remain. These guards prevent cross-use and do not
   implement or authorize a candidate maintenance namespace. Old audit code hashes
   and descriptors must remain unchanged; invoking revised code requires separately
   reviewed fresh code manifests/approvals, not reusing a historical authorization.
2. Provider shared/generated identity, default/readback and real instance State
   schema compatibility remain unproven. In particular, API Gateway Integration
   identity registration and the new SNS computed value require explicit assessment.
   No State data has been accessed. Any actual AWS/State assessment requires fresh
   account/environment/SHA/scope/cost/recovery authorization.
   Explicit outstanding evidence includes computed/default values, identity/import
   behavior, State upgrader behavior, real resource differences, and AWS readback
   agreement. Equal provider resource schema versions or successful synthetic/no-op
   comparisons do not prove these properties or real State compatibility.
3. New saved Plans/bindings/approvals must bind exact CLI/platform, provider locks,
   source, inputs, Plan bytes and State identity. Historical authorizations/Plans
   cannot be migrated, even when synthetic JSON readers or mocks pass.
4. Independent adoption/security review, final-HEAD genuine required Actions, and
   explicit approval to release the formal-upgrade HOLD are required before merge.
   Self-review is not independent review. No approval is implied by this Draft.

The existing High finding about the current runtime's CA security fix stays open
until qualified adoption. This draft is concrete review input, not a claim of
complete operational readiness. Keep this PR Draft and unmerged until all blockers
are independently resolved and the user releases HOLD.

## Local validation

### CI follow-up and independent review (2026-10-25 JST)

At starting HEAD `63cb7db7e994cba08404655804a4a8cc863439a9`, all four genuine
pull-request workflows succeeded: Backend `40161158192` (2448 passed, 2 skipped,
57 deselected; 102 API contract tests), Frontend `40161158191` (669 tests, 37 mock
E2E), Terraform/package `40161158189` (six scopes, 69 mocks and actual Linux ZIP
build/import), and candidate matrix `40161158163` (1.16.7 and 1.17.0). Historical
failed Ruff runs are superseded by these exact-HEAD results, not silently retried.

An independent read-only code/security review found the late legacy version gate,
the unbounded lifetime of the migration-only matrix, and malformed
`proposed_unknown` containers being accepted by the generic unknown-mask recursion.
The follow-up fixes these with regression tests. A second review caught normal
`sensitive_values` metadata being over-rejected and PATH resolution ignoring the
supplied environment; both were corrected. This is an independent code review,
not an operational adoption approval or evidence of real AWS/State compatibility.

`proposed_unknown` now validates its values-representation containers separately
from unknown masks; known metadata and sensitivity masks remain distinct. Malformed
root/module/resource/output containers and unknown or non-boolean value leaves fail
closed on either side of the comparison. The existing Closure test still uses real
CLI arguments, exact ValueError outcomes, and both rejected/accepted authentication
ordering. It does not treat argument-parser SystemExit as a successful regression.
The focused compatibility/candidate suite passes **111 tests** using Python 3.14.9
and uv 0.13.5. Full suite and final-HEAD Actions results are recorded in the PR.
On this Windows host, the inherited PowerShell 7 `PSModulePath` prevented the
Windows PowerShell child from loading `Microsoft.PowerShell.Security` for ACL
checks. The failing synthetic ACL tests pass with the child execution environment
using `%WINDIR%/System32/WindowsPowerShell/v1.0/Modules`; no ACL gate is bypassed,
no persistent host setting is changed, and no production evidence is touched.

Official references consulted for the boundaries:
[Terraform JSON values representation](https://developer.hashicorp.com/terraform/internals/json-format),
[backend-disabled init](https://developer.hashicorp.com/terraform/cli/commands/init),
[GitHub PR events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

### Earlier PR B qualification (retained historical result)

Related runtime/version/binding/schema/closure/deployment/standard-CI tests:
**304 passed**. Ruff check/format, native candidate `fmt -check -recursive`,
`git diff --check` pass. The exact migration validator was run against this branch's
actual Terraform bytes and the unchanged legacy checkout: only the six CLI/provider
requirements and six generated lockfiles differ. Native six-scope candidate validate
and 69 mocks were already completed for those exported Terraform bytes; this is not
a fresh real AWS or State run. Genuine current-HEAD CI is recorded on the Draft PR.
