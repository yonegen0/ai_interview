# Stage2 standard GitHub/AWS execution

2026-10-24: current read-only qualification uses [verification v2](STANDARD_OIDC_VERIFICATION_V2.md).
Historical approval recipes below remain history; current owner autonomy policy in AGENTS.md takes precedence.

2026-10-21 JST. Method B is adopted by the user. This source is a local candidate;
GitHub changes, credentials, CI, AWS, official Plan/Apply and release are not approved.
READY=false; formal_resume_ready=false; STAGE2_V6_STOPPED_NOT_SUCCESS.

## Implemented route

`p4-standard-plan.yml` and `p4-standard-apply.yml` are separate manual workflows.
They reuse `ci_deploy.py`, `terraform_dev.py`, the existing Plan authorization and
run-history consumption, S3 versioned transport, binary digest/binding checks and
conditional Apply journal writes. No Hello key, local signature app, custom issuer,
nonce, claim or new approval database is required by this route. Existing legacy
workflow definitions and old evidence are retained until safe migration is verified.

Both workflows require protected current main, the approved commit SHA, repository
ID 1361325921, owner/operator ID 76547980, original and triggering operator, correct
workflow ref/SHA, workflow_dispatch, first attempt and a 72-hour issue/expiry window.
Plan also retains its existing immutable approval package and recipient certificate;
these bind artifact/configuration/expiry and provide encrypted evidence, not Hello
identity. Approval values remain unissued until an explicit external approval.
Apply is a separate dispatch with its own issue/expiry, Plan run ID and binary SHA.
Plan dispatch does not start Apply. Reruns are refused; the first matching dispatch
consumes the operation, including failed/queued runs. Do not delete run history.

`P4_STANDARD_READY` must remain absent/false until the external preconditions below
are actually verified. `P4_AWS_EXECUTION_READY` is a separate existing switch.
Main-only Environment branch policies, no administrator Environment bypass, and
protected main are checked before AWS credentials. This is not a full ruleset/check
App/bypass audit: that fresh audit is an explicit precondition to opening the switch.

## Roles and IAM cutover

`terraform/bootstrap/standard-ci.tf` is additive and disabled by default:

| New role suffix | Exact Environment subject suffix | Permissions reused/restricted |
|---|---|---|
| plan | dev-plan | Existing project read/identity read; State read and normal lock writes; no deploy/IAM mutation |
| artifact-plan | dev-plan | Lambda ZIP and Plan files only; no Apply journal writes |
| deploy | dev-apply | Existing project-scoped deploy/state/identity policy ceiling |
| artifact-apply | dev-apply | Plan reads and Apply journal/deployment receipt writes; no ZIP/Plan writes |

Each full role name is `ai-interview-standard-ci-<suffix>`. Trust uses StringEquals
for aud=sts.amazonaws.com and
`repo:yonegen0@76547980/ai_interview@1361325921:environment:<environment>`.
No wildcard sub, no environment-free fallback. Main is separately restricted by
Environment branch policy and workflow checks; an Environment sub does not itself
encode a branch. New role maximum/session duration is 3600 seconds. AWS verifies
the OIDC signature; the local payload checks alone are not signature verification.
Existing IAM policy ceilings contain some wildcard read/list actions and scoped
deployment management permissions; no claim of proven global least privilege or
effective IAM is made. Real allow/deny and actual trust readback are still required.

Order, each external phase separately approved:

1. Obtain read-only actual main/protection/check App/review/contract/Environment
   facts and canonical bootstrap State identity using approved principals. Do not
   assume saved refs are current. Confirm an independent operator recovery principal
   whose access does not depend on the legacy dev subjects being retired.
2. Publish the standard-only patch by protected PR, run required genuine CI and
   merge only after checks/review/protection pass. No AWS-capable workflow dispatch
   and no standard-ready switch yet. Confirm every automatic trigger and its cost.
3. In a reviewed canonical bootstrap workspace, separately approve a new native
   saved Plan with `standard_ci_enabled=true, legacy_ci_retired=false`. Review the
   complete Plan, then separately approve that same binary for Apply. Expect only
   four new roles/four inline policies and corresponding output; unrelated baseline,
   Bedrock, State migration, provider/version and runtime changes are forbidden.
   Actual source/State/Plan SHA and resource differences must be fixed from evidence.
4. Configure `dev-plan` and `dev-apply`, selected branch type=branch/name=main only,
   no admin bypass, scoped copies of existing required Secrets, readiness=false.
   Confirm immutable OIDC subjects and actual role policies. Read-only/negative
   qualification of new roles needs its own approved call graph; no service Plan
   is smuggled into identity qualification. Do not replace or delete old roles first.
5. With independent recovery access confirmed and new role qualification successful,
   separately Plan/review/Apply `legacy_ci_retired=true` in canonical bootstrap.
   This changes old four trust statements to Deny, without deleting their roles or
   old evidence. Account for already-issued legacy STS sessions: stop legacy issuance,
   wait the verified maximum remaining session lifetime (up to old role max 7200s),
   or use separately approved session revocation. Changing trust alone does not
   revoke sessions. Keep standard-ready=false until this window and readback finish.
   Legacy test/upload/deploy workflows will then fail closed; they are not certified
   for the new route and must not be used as a fallback. Independent AWS test roles
   and any later enablement/closure remain separate approval scopes.
6. After protection, trust, session expiry and qualification evidence pass, open the
   standard switches under explicit approval. First standard Plan dispatch: one
   attempt, one saved Plan, Apply0. Review the same saved binary using independent
   show/full-diff, original S3 VersionIds, State identity/no-lock and private evidence.
7. Only then issue a separate Apply approval/dispatch binding current unchanged main,
   exact Plan run and SHA, fresh expiry, target/role/cost and stop conditions. No
   automatic chaining, replan, rerun, force-unlock or rollback. Failed/unknown Apply
   leaves the S3 started record and stops; it is not permission for another Apply.

The old `bootstrap_maintenance.py` is deliberately limited to the historical
32-resource/state-policy repair. It cannot execute this new IAM migration and must
not be passed these flags or have its whitelist silently widened. Use a separately
reviewed native Terraform canonical-bootstrap Plan/Apply scope with independent
operator access. The source's native Terraform implementation is prepared; the
actual workspace, bootstrap principal, current State and commands still require
authorized read-only evidence before that external approval can be concrete.
Never run bootstrap creation, init migration, or consumed Apply002 to do this work.

## Standard UI and guarantee differences

The user supplied actual GitHub observations on 2026-10-21: the repository is public,
observed main is `ca4d7976e779473b6d0650f9f69484705bdb5798`, and ruleset 24886774
is active with PR required, strict checks, zero required approving reviews, resolved
review threads, and non-fast-forward/deletion restrictions. Required check names are
`Backend verify`, `Frontend verify`, `terraform`, `package_changes`, and `package`.
The connection returned an empty bypass list; this alone does not certify complete
bypass visibility or resolve the old App's 403. The existing `dev` has one protection
rule, five Secrets and one Variable; their contents are not inferred. `dev-plan` and
`dev-apply` do not exist. Reuse these observations; refresh mutable facts just before
publication/execution instead of asking for the same existence evidence again.

For one operator, separate manual dispatches are the recommended practical mode,
subject to the explicit guarantee decision below. Use independent required reviewers
when an eligible second person is available. Public repositories support reviewers
on current plans, but actual settings and enforcement still need verification. Do
not change visibility, upgrade a plan, or weaken existing protection to make this
route fit. If Environment/main protection is unavailable, do not enable.

Set `P4_STANDARD_REVIEW_MODE=reviewers` when verified. The API check requires the
operator as a required User reviewer. Prevent-self-review must match the actual
reviewer/dispatcher arrangement; do not disable existing protection just to unblock
a single-person run. If unavailable, `manual` uses two explicit operator UI
dispatches with the same checks. In either mode, use GitHub Actions > the matching
workflow > main > the exact approved inputs > Run workflow. Review the new run and
never use Re-run jobs. Keep Plan and Apply approvals separate.

Manual mode does not provide GitHub's server-enforced reviewer approval. The
workflow/operator checks rely on protected workflow definitions and Environment
configuration. Repository administrators can alter these controls or delete history;
neither manual dispatch nor concurrency prevents a malicious administrator. PR
review/required checks/non-bypass and audit retention are mandatory. This must be
explicitly reviewed before external cutover, not inferred from method-B adoption.
GitHub records replace arbitrary-text RSA-PSS signature and same-handle W1 witness;
those cryptographic guarantees are not retained or described as equivalent.

## Exact Environment recipe (not an issued setting approval)

The workflows resolve these names through the selected job Environment. Do not
add long-lived AWS keys, Role-ARN Secrets, or `P4_OIDC_SUBJECT` Variables: the exact
subject and the four purpose-specific Role names are already bound in source.

| Environment | Secret name | Workflow reference and purpose |
|---|---|---|
| both | `AWS_DEV_ACCOUNT_ID` | `secrets.AWS_DEV_ACCOUNT_ID`; explicit target account |
| both | `P4_DEPLOY_INPUTS` | `secrets.P4_DEPLOY_INPUTS`; validated closed service configuration, with no artifact overrides |
| dev-plan only | `P4_PLAN_APPROVAL_PACKAGE` | `secrets.P4_PLAN_APPROVAL_PACKAGE`; fresh immutable package issued only under the later service-Plan approval |
| dev-plan only | `P4_PLAN_EVIDENCE_CERT_PEM` | `secrets.P4_PLAN_EVIDENCE_CERT_PEM`; certificate of the existing approved evidence recipient, never the private key |

These are requirements, not a claim that any existing Secret matches. Values are
UNKNOWN. Do not read, display, export, or clone the five `dev` Secrets. A user with
the trusted original values can later enter the required names in GitHub UI; no
plaintext is submitted in chat. Do not copy an old approval package. Apply has no
Plan-package or evidence-certificate Secret. Approval SHA, certificate SHA and
Plan run/hash are explicit dispatch inputs, not additional Environment Variables.

Both Environments need exactly these initial Variables (the `vars` references in
the workflows): `P4_STANDARD_READY=false`, `P4_AWS_EXECUTION_READY=false`, and
`P4_STANDARD_REVIEW_MODE=manual` for the proposed single-operator mode. The last
value becomes `reviewers` only if that mode is selected and configured. Keep both
readiness switches false throughout Environment setup, PR/CI and IAM migration.

After explicit approval, one UI session at Repository Settings > Environments:

1. Create `dev-plan`, then `dev-apply`; preserve `dev`. Do not run any workflow.
2. For each, select **Selected branches and tags**, add exactly one rule with
   **Ref type=Branch**, **Name=main**. Add no tag, wildcard or PR-ref rule.
3. Clear **Allow administrators to bypass configured protection rules** and save.
   If the UI cannot persist this setting, stop; do not relax the code check.
4. In approved manual mode, leave Required reviewers unset on the new Environments.
   In independent-review mode, the current code requires `yonegen0` in the reviewer
   list; include that user plus the independent eligible reviewer and enable
   **Prevent self-review**. The initiating operator then cannot approve the job;
   the independent reviewer must approve. Operator-only plus Prevent self-review
   would block deployment. Do not change the existing `dev` rule to resolve this.
5. Set the three Variables above in each Environment and read back the saved rules
   and Variables. Initial creation requires zero Secret writes. Secret provisioning
   and the fresh Plan package remain separate, later qualification/Plan scopes.

Initial setup therefore authorizes only two Environment creations, two protection
saves, two main branch-rule additions and six Variable creations (12 UI saves),
with AWS calls, dispatches, Secret access and existing-Environment changes all zero.
New Roles are still absent/disabled and both readiness switches remain false; an
incomplete Environment is never used to request AWS credentials. Missing required
Secrets stop qualification instead of being guessed or recovered from `dev`.

Manual mode removes the independent server-side reviewer gate, arbitrary-text
RSA-PSS signature and same-handle witness. Main/operator/SHA/run checks, separated
purposes and approval windows remain, but administrators can change controls or
remove history. The user must explicitly accept this difference once before the
new Environment configuration; method-B adoption alone is not that acceptance.

## Standard-only PR publication scope (not issued)

The standard patch applies to observed main `ca4d7976e779473b6d0650f9f69484705bdb5798`
in a temporary Git index without changing the real index or worktree. The candidate
also contains unpublished STAR/Bedrock work. Publish the **patch applied to actual
base files**, not whole candidate files: in particular the standard `main.tf` hunk
changes legacy trust only; copying that whole candidate file would also introduce
an unpublished Bedrock reference. Do not include PRODUCT_CHANGES.patch.

Bootstrap validation uses that base plus exactly the three standard Bootstrap paths,
the existing lock-matching Windows AWS Provider 6.64.0, and Terraform 1.14.9. It
uses no init, backend, real State or credentials. A native mock exposed incompatible
conditional tuple types in the new deploy-policy composition; filtered statement
comprehensions preserve the same Plan/deploy permissions and fix the evaluation.
Final logs and accepted test counts are in the release-candidate checkpoint.
This is mock evidence, not effective IAM or a formal AWS Plan/Apply.

Proposed publication: existing GitHub connection, branch
`codex/standard-stage2-20261021-001`, one standard-only tree/commit and one PR to
main, merge/rerun/extra push zero. Connector writes are bounded to 12 blobs,
one tree, one commit, one branch creation and one PR (16 calls). Apply the pinned
patch to the approved base in memory; use the observed base tree and parent. Record
returned tree/commit/PR values once; do not invent future SHAs. Reconfirm main,
repository identity, active rules/check source Apps, bypass visibility, existing
branch absence and current CI/Actions permissions before the first write. If main
is different, stop before publishing and adapt locally under a new concrete scope.

Creating the branch can trigger Backend and P4 static runs; opening the PR triggers
Backend, Frontend and P4 static runs: allow at most five automatic workflow runs
and nine job records, including a skipped package job. First-branch publication
requires full package verification by the existing package detector. The PR-only
standard delta leaves package inputs unchanged and may skip that job; skipped is
not a successful package build. Retain all five required check names. Linux CI must
execute the two existing `test_cloud_ci` POSIX/seccomp cases without Windows skips.

Read-only connector checks/polling/log retrieval are bounded to 60 tool calls and
90 minutes within the new 72-hour approval. Connector-internal HTTP counts are not
observable and are not represented as a REST hard cap. Unknown/paginated/truncated
evidence, 401/403, source/protection drift, occupied branch, failure, unexpected
trigger, fee requirement or uncertain write stops further writes; no automatic
credential/transport switch or retry. Evidence stays in the existing private
artifact area under a new dedicated child, never over old journals.

Actions contract/usage/storage charges remain unconfirmed. The proposed scope
permits existing standard GitHub-hosted runners only, no paid runner, plan upgrade,
spend-limit increase, paid inference or AWS run; incremental paid spend authorized
is zero. Verify the actual account's applicable terms/usage before publishing;
do not describe this call limit as a billing hard cap. Normal merge and its main
CI are a later approval. Environment setup and PR publication are independent
scopes; acceptance of one does not issue the other.
Official [runner billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
states that standard runners are free for public repositories; artifact/cache
allowances and any account-specific storage charges still need actual confirmation.

## Old eight Gates consolidated (classification, not live completion)

| Old Gate | Standard route |
|---|---|
| UI-B/Hello | Operator dispatch and available reviewers; arbitrary-byte signature removed with guarantee difference above |
| PAT/W1 | Standard UI/GITHUB_TOKEN and short-lived OIDC; real API credentials/scope still separately approved |
| E-B | Absolute 72-hour approval and credential expiry, insufficient-time refusal retained |
| authority | GitHub issuer plus exact AWS OIDC trust; custom issuer removed for this route |
| W2/protection | Fresh effective Rulesets/check App/review/bypass confirmation by authorized API or complete genuine GitHub UI evidence |
| claim/root | Existing first-dispatch history and conditional S3 journal; private storage/version/hash retained; custom local claim not required |
| lease | Existing deadlines/timeout, shared concurrency and State lock; no new host lease; outcome-unknown stop retained |
| Linux/log | Genuine Linux3.14/native ZIP and bound run/attempt/source/ciphertext evidence retained |

Ruleset GET403 is unresolved. GET access, actual App/PAT identity and visibility of
all bypass actors are separate facts. Full genuine UI review is an alternative
evidence path, not proof that the failing API now works. No token discovery or
permission expansion occurs automatically. A 401/403/unknown automated observation
stops that operation; no silent change of transport or credential/retry.

## Approval review queue (none issued)

| Order | Target/action/count | Fixed binding and outstanding evidence | Deadline/cost/stop |
|---|---|---|---|
| 1 | Initial Environment setup: 2 creations, 2 protection saves, 2 branch rules, 6 Variables; Secrets/AWS/dispatch0 | Exact recipe above; one explicit manual-mode guarantee decision; preserve dev; reuse the user's existing observations | New 72h approval; at most 12 UI saves; both readiness switches false; stop unsaved protection or scope mismatch |
| 2 | Standard-only publication: 12 blobs/tree1/commit1/branch1/PR1; up to 5 automatic workflow runs/9 job records; merge0/rerun0 | Current patch SHA and 12 publication hashes in CHECKPOINT; pre-write main must still equal approved observed base; actual head/PR values remain null | New 72h approval; read tools60/monitor90min; verify no incremental paid spend; normal merge and its main CI need later separate approval |
| 3 | Canonical bootstrap additive IAM Plan1, then separately same-binary Apply1 | Independent principal, Account/Region, State VersionId/lineage/serial/hash, source/lock SHA and saved Plan SHA currently unset | 72h each; lock/partial/unknown/diff outside whitelist stops; AWS/Actions cap to be fixed from actual call graph |
| 4 | Environment configuration and read-only role qualification, then separate trust-retirement Plan1/Apply1 | Exact new subjects and policies, main-only rules, non-bypass, Secrets names; no secrets in chat | Counts/principal/session waits/cost fixed before execution; unknown qualification leaves old route and switches closed |
| 5 | Standard service Plan workflow dispatch1/attempt1/Plan1/Apply0 | Published current source SHA, package/configuration hashes, existing recipient, approval package; no old P payload | New 72h approval; existing guard budgets plus actual GitHub/AWS calls require review; no blind reuse of Q/P budgets |
| 6 | Standard Apply workflow dispatch1/attempt1/same binary Apply1 | New independent approval, successful standard Plan run/attempt1, source SHA, binary SHA and S3 versions | New 72h approval; stop expiry/credential mismatch/lock/partial/unknown; no refresh/retry/replan |
| 7 | AWS/Bedrock/E2E/performance/conditional Closure/release | Real API/Cognito public identifiers, least-IAM allow/deny, model/profile destination ARNs, new artifact/version/alias | Separately bounded calls and fees; C63 nearest-rank p95<=2s unchanged; paid inference/deployment/publication not authorized |

No approval ID, actual issue time, run ID or Plan SHA is invented here. Descriptors
must include actual cost limits and that budget alerts are not a billing hard cap.
Product import optimization remains PRODUCT_CHANGES.patch; this migration is
STANDARD_CHANGES.patch. Do not put that product patch or the old formal 3-path/P
payload into this publication scope. STAR/Coaching/Frontend/Bedrock runtime source
is unchanged during this work; previous product/mock results are reused with limits.

Official sources checked 2026-10-21: [Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[OIDC/AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[GitHub contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).
These documents are not proof of this repository's live configuration or effective IAM.
