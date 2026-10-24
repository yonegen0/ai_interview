# Standard OIDC read-only verification v2

The owner delegated routine development, protected PR merges and development AWS
validation on 2026-10-24. Historical fixed-patch approvals remain preserved; they
are not reused. This workflow does not claim the historical CMS Phase D success.

Run `P4 standard read-only OIDC qualification` on current protected `main`, with
`source_sha` set to that reviewed commit. The existing `dev-plan` and `dev-apply`
Environments restrict branches to main and keep both service readiness flags false.
`AWS_DEV_ACCOUNT_ID` must come from the trusted existing account record; never guess
it or pass credentials as workflow inputs. No recipient certificate is needed for
this read-only check. Existing service Plan/Apply workflows still have their own
contracts and are not relaxed by this change.

Each Environment checks two existing standard roles. AWS STS validates the GitHub
token signature and trust conditions. The reader checks repository/owner IDs,
main/source/workflow/Environment/run/actor claims, exact caller identity, short
session expiry, Tokyo bucket location, denied standard-role reads and denied
cross-Environment assumption. All assumed sessions have read-only restrictions.
No Terraform, IAM modification, service writes, credential discovery, SDK retries
or automatic fallback occurs. There are ten AWS requests per Environment: six
expected successes and four expected denials. An unexpected result fails the job.

`denied-standard-role-read` calls IAM GetRole on the same existing
`ai-interview-standard-ci-<suffix>` role that issued the session. These are
bootstrap-managed CI roles, outside the runtime-role read scope in
`terraform/bootstrap/ci-policies.tf`; artifact roles have no IAM read Allow.
The session policy explicitly allows GetRole on that exact target, subject to
the common expiry Deny, so a missing session-policy Allow cannot satisfy this
probe. This demonstrates effective denial for this target/session at that time;
it does not isolate every possible policy layer or prove all role permissions.
There is no change to AWS role permissions or trust.

Expected denials require the SDK operation name, a nonempty request ID and HTTP
403 as well as an operation-specific error code: GetRole permits AccessDenied
or AccessDeniedException; AssumeRoleWithWebIdentity permits AccessDenied only.
Expired credentials, signature/authentication failures, missing entities, other
403s and unexpected successes fail. See [IAM common errors](https://docs.aws.amazon.com/IAM/latest/APIReference/CommonErrors.html)
and [STS session policy semantics](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html).

The two jobs upload only an allowlisted JSON result (at most 32 KiB each), retained
seven days. It contains source/reader hashes, run/attempt/Environment, operation
outcomes and verified session timestamps. Account numbers, bucket names, ARNs,
request IDs, token/credential bodies, raw exceptions and private journals are not
uploaded. Private details exist only in the ephemeral runner. Hosted job steps,
the reviewed source SHA and both result files are required to accept v2 verification;
an artifact or HTTP200 alone is insufficient. This deliberately does not provide
decryptable detailed CMS evidence or prove unseen IAM permissions.

Stopped results additionally expose only `failure_stage` and `failure_class`
from fixed source allowlists. For example, `bucket-region-validation` distinguishes
the S3 LocationConstraint comparison from `denied-standard-role-read`; AWS error
codes, request IDs and raw error messages remain private. Successful results omit
these diagnostic fields. Run 40050538250's three successful checks do not identify
which of these two stages stopped: its actual remote exception was not published.
The explicit global IAM endpoint's Tokyo signing scope was reproduced offline and
corrected to us-east-1, and the IAM AccessDeniedException rejection was reproduced
and corrected, without claiming either was the observed remote exception.

Collect partial results after a failure without rerunning a result-unknown operation.
The existing independent AWS access route is required before retiring legacy trust;
trust retirement does not revoke existing sessions. Do not retire trust or apply a
new Plan until the replacement path is actually verified.

Frontend failure reports are selected into an archive capped at 10 MiB, with an
8 MiB input budget and three-day retention. Omitted diagnostics are marked as a
partial report; this never changes the failed test result. Billing settings and
repository cache limits remain unchanged. Inspect actual uploaded sizes rather
than inferring unlimited storage from free public runner minutes.
