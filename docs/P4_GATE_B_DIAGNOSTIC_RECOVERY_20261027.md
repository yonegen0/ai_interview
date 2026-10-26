# Gate B residual audit and recovery preparation — 2026-10-27 JST

Run 40336463379 / Attempt 1 remains FAILURE. Terraform's normal exit remains
UNKNOWN. A valid started receipt, absent completed/deployment receipts, and State
serial 12 -> 13 do not identify the failing stage. The Stage access-log format
differs from Plan/State13; this is not proof of the original failure cause.

## Reproduced offline defect

The approved-input verifier previously compared budget strings literally:
normalized `10.00` versus Terraform number-to-string `10`. Compare only this
field using finite Decimal values, preserving exact comparisons of every other
configuration field and avoiding mutation of either input. Different amounts,
non-finite values and invalid numbers still fail. No budget amount changes.

The defect can obstruct a later manifest readback but does not explain why the
earlier completed receipt is absent. No historical exit or receipt is synthesized.

## Residual diagnostic design

Use a separately approved, one-use private package bound to original Run/source,
saved Plan and State13 lineage/serial/S3 VersionId/byte hash. Preserve and verify
diagnosis001/002 evidence indexes and consumed approvals. Reuse the eleven
historical changed-field matches with timestamps; they are not current proof.

Read all sixteen new routes in an API-scoped GetRoutes collection, following
bounded pagination. Compare API, RouteId, RouteKey, Target, AuthorizationType and
AuthorizerId with concrete planned fields and State-resolved computed identities.
Read all five known log groups and compare retention. Compare both Stage format
strings and parsed JSON; whitespace/key ordering is not a structural difference.
Limit additional invariants to known authorizers/integrations, Cognito, runtime
IAM roles and existing notifications/budget/alarms. Never repeat the full prior
verifier or successful unrelated tests solely for completeness.

Configuration differences become per-resource evidence and do not stop remaining
known-resource reads. Unknown exceptions, permission/authentication failures,
account/region changes, State identity/hash changes, locks, unexpected readiness
or public entry enablement, tampering and limits remain fatal. Always perform
fresh ending State/no-lock/closure/readiness checks after ordinary differences.
After a fatal stop, preserve partial/unknown rows without making further reads.

Reference APIs: [GetRoutes](https://docs.aws.amazon.com/apigatewayv2/latest/api-reference/apis-apiid-routes.html)
and [DescribeLogGroups](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_DescribeLogGroups.html).
The private approval fixes actual request/time/cost/expiry limits; this document
does not authorize any AWS access.

## Recovery decision after the audit

| Method | Reproducibility / audit | Operations and costs | Decision |
| --- | --- | --- | --- |
| A: new Terraform Plan, separately approved saved-Plan Apply | Preferred managed-state path; detect drift and reject unrelated changes; bind new source/input/State/Plan hashes | New authorized Plan then exact-Plan approval; request count, Actions cost and AWS estimate must be computed for that package | Provisional recommendation; finalize after all residual differences are known |
| B: one UpdateStage | Candidate only if Stage Format is the sole difference, independently matches code/Plan/State, and direct repair leaves management consistent | One exact Format update plus pre/post GetStage and fresh State/closure checks; prepare separate limits after audit | Conditional alternative; no authorization now |
| C: State repair | Can hide or alter intended managed truth; final resort | Separate high-risk approval and recovery safeguards | Excluded at this stage |

A's Plan and Apply require distinct authorization because the exact Plan cannot
be approved before it exists. Bundle each operation with its identity checks,
closure checks and evidence handling. Do not reuse old approvals. B requires
its own fixed API/Stage, exact before/after Format and one-use update approval;
the read-only diagnostic approval cannot authorize it. No repair cost or total
billing cap is promised before its exact execution package is reviewed.

## Narrow prevention proposal

These are future design items, not changes to the formal workflow in this PR.

| Boundary | Minimal safe record |
| --- | --- |
| Terraform subprocess | Attempt ID, fixed executable/Plan identity, started/returned flag, numeric exit code, timestamps; durably record completion before receipt-role switching |
| Failure stage | Fixed stage/reason enum for preflight, Terraform, local completion journal, receipt credential acquisition, receipt PUT, manifest readback and final deployment receipt |
| Receipt | Record intent, response/VersionId verified, uncertain outcome separately; never infer absence from access denial or recreate a receipt after an unknown result |
| Manifest | Distinguish configuration differences, authorization, transport, schema and identity failures; retain per-resource differences in a separately approved read-only collector |
| Diagnostics | Only fixed codes, file/function/line and allowlisted request IDs/status; no raw exception text, tokens, emails, State or Terraform stdout in public logs |
| Encrypted journal | Reuse the existing reviewed CMS journal path; add standard-mode recording/upload only in a separately reviewed workflow change, with no new role permissions or plaintext artifacts; preserve local failure evidence if upload fails |

Missing logs/receipts cannot distinguish Terraform failure from local I/O,
receipt persistence, credential reacquisition, later readback, partial apply or
external configuration changes. New evidence may narrow these possibilities;
configuration repair alone cannot retrospectively prove normal Terraform exit.

After separately approved recovery and State/AWS/closure verification, return to
release readiness review. OTP, paid inference, live E2E/performance, enablement and
publication retain their separate approval boundaries. Formal Terraform remains
1.14.9, Issue #50 OPEN and PR #43 Draft/HOLD.
