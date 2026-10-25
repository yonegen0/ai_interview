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
  The normal `terraform` required
  check separately validates the actual PR B configuration at its proposed version.

To repeat migration qualification locally, pass a separate checkout of that legacy
source as `--repository`; the migration runner intentionally rejects already-upgraded
configuration as its baseline. All generated work must remain disposable and offline.

## Merge blockers — passing CI alone cannot release HOLD

1. **Future bootstrap maintenance/recovery execution remains incomplete.** Current
   readers/executors retain the old source/CLI contracts. Preserve their original
   checkout, toolchain, approvals and receipts. They must not be run against the new
   bootstrap HCL or silently allowed to accept a candidate version. A separate future
   operation/approval namespace and reviewed execution path are still required.
2. Provider shared/generated identity, default/readback and real instance State
   schema compatibility remain unproven. In particular, API Gateway Integration
   identity registration and the new SNS computed value require explicit assessment.
   No State data has been accessed. Any actual AWS/State assessment requires fresh
   account/environment/SHA/scope/cost/recovery authorization.
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

Related runtime/version/binding/schema/closure/deployment/standard-CI tests:
**304 passed**. Ruff check/format, native candidate `fmt -check -recursive`,
`git diff --check` pass. The exact migration validator was run against this branch's
actual Terraform bytes and the unchanged legacy checkout: only the six CLI/provider
requirements and six generated lockfiles differ. Native six-scope candidate validate
and 69 mocks were already completed for those exported Terraform bytes; this is not
a fresh real AWS or State run. Genuine current-HEAD CI is recorded on the Draft PR.
