# Stage17 recovery

The failed Apply run 40875185933 is correlated with CloudTrail UpdateStage at
2026-10-29T12:43:19Z (request ID 3c68b451-622c-4cdd-b0b2-feb2e4dc3675).
Its BadRequestException response explicitly reports no identity-based Allow for
`logs:UpdateLogDelivery` on the standard deploy role. The actual role has one
inline policy, no attached managed policies and no permissions boundary. Its
existing five logging actions match source. IAM simulation allows all five and
implicitly denies UpdateLogDelivery and DeleteLogDelivery. The account is the
organization management account, where SCPs do not restrict principals.

Add only UpdateLogDelivery to the existing opt-in Tokyo statement. The pinned
Provider 6.65.0 updates the existing Stage with AccessLogSettings; the destination
is unchanged, and no log-delivery deletion is in this operation. DeleteLogDelivery
is listed in the full AWS logging lifecycle policy, but is not required by this
format-only update and is not added. No trust, boundary, runtime role or public
entry changes are included.

Sources: [HTTP API logging permissions](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html),
[Provider Stage update](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/stage.go),
[SCP scope](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html).

Fresh readback confirms Bootstrap serial7/40 resources, dev serial17/77 resources,
both locks absent, live Stage four fields versus State six fields. All dev
resource attributes match the previous post-failure snapshot. The existing schema3
also accepts serial17 only with this exact failed run, Plan, started receipt and
16-to-17 transition. Existing snapshot/hash/full-resource checks remain. Old
approvals and Saved Plans cannot be reused. A finite UpdateLogDelivery diagnostic
hint improves failure classification without exposing provider error text.

Next: merge after required CI; generate and audit one new canonical Bootstrap
Plan allowing only this policy update, then obtain human approval of its exact
Saved Plan SHA256. Apply once and independently read back all 40 resources. Only
then generate the fresh Stage-only Plan with all 77 resources and 10 IAM no-ops,
obtain its own exact Saved Plan approval, Apply once and read back State, Stage,
receipts, four closed entries and readiness=false. Stage recovery, real AI/E2E,
performance and Hosting remain uncompleted until measured.
