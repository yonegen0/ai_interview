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
session expiry, Tokyo bucket location, denied bootstrap-role reads and denied
cross-Environment assumption. All assumed sessions have read-only restrictions.
No Terraform, IAM modification, service writes, credential discovery, SDK retries
or automatic fallback occurs. There are ten AWS requests per Environment: six
expected successes and four expected denials. An unexpected result fails the job.

The two jobs upload only an allowlisted JSON result (at most 32 KiB each), retained
seven days. It contains source/reader hashes, run/attempt/Environment, operation
outcomes and verified session timestamps. Account numbers, bucket names, ARNs,
request IDs, token/credential bodies, raw exceptions and private journals are not
uploaded. Private details exist only in the ephemeral runner. Hosted job steps,
the reviewed source SHA and both result files are required to accept v2 verification;
an artifact or HTTP200 alone is insufficient. This deliberately does not provide
decryptable detailed CMS evidence or prove unseen IAM permissions.

Collect partial results after a failure without rerunning a result-unknown operation.
The existing independent AWS access route is required before retiring legacy trust;
trust retirement does not revoke existing sessions. Do not retire trust or apply a
new Plan until the replacement path is actually verified.

Frontend failure reports are selected into an archive capped at 10 MiB, with an
8 MiB input budget and three-day retention. Omitted diagnostics are marked as a
partial report; this never changes the failed test result. Billing settings and
repository cache limits remain unchanged. Inspect actual uploaded sizes rather
than inferring unlimited storage from free public runner minutes.
