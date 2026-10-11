# Closure P1 offline fixes (2026-10-11)

Base: `9cbdc06b8791a0237b1b48564df59d2c4469a697`.
Review findings: R1/R2 in `CODE_REVIEW_SINCE_6F211F3_20261011.md`.

## R1: clean execution source

The old Git pathspecs were relative to `terraform/environments/dev` and missed
changes in the root runtime, helper and Terraform directories. Root-anchored
`:(top)` pathspecs now reject staged/unstaged tracked changes and untracked
runtime helpers or Terraform overlays before establishing the AWS session.
Five disposable Git repository regressions exercise the actual subdirectory cwd.

## R2: computed mapping metadata refresh

Closure used to reject all `resource_drift`, including normal service metadata
refresh after Smoke/performance traffic. It now audits each refresh independently:
only the exact Worker/Streams mapping addresses, update actions, bound original
State attributes and three computed fields (`last_modified`,
`last_processing_result`, `state_transition_reason`) are permitted. The saved-plan
resource change must start at precisely that audited refreshed value.

Identity, Enabled/state, scaling configuration (including MaximumConcurrency),
other resource drift, unknowns, replacements, duplicate refreshes, moved/deposed
instances and unbound values remain rejected. Planned changes retain the same
four-update/approved-Alarm-delete whitelist. Readback inventory and closed State
checks are unchanged.

[Terraform JSON documentation](https://developer.hashicorp.com/terraform/internals/json-format)
defines resource_drift as the comparison with prior saved State.
[AWS provider v6.65.0 source](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v6.65.0/internal/service/lambda/event_source_mapping.go)
defines the three fields as computed strings and reads them from the service.
This matches the dev lockfile; the original review's v6.64.0 definitions were
also checked and unchanged for these fields.

## Verification and scope

Targeted offline suite: 70 PASS; Ruff and Git whitespace checks PASS.
Fixtures prohibit socket/SDK transport. No AWS connection, real Terraform
plan/apply/destroy, production State, saved Plan, journal or binding modification.
Windows Python 3.14 synthetic fixture mkdir used inherited ACLs via a dedicated
evidence-directory launcher; implementation privacy/security gates were unchanged.

Source fingerprints change, so future Enablement/Closure approvals must bind the
new reviewed source. Existing successful validation evidence remains preserved;
this PR does not authorize re-enablement or a live Closure operation.
