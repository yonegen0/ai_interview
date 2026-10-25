# Issue #39 — candidate bootstrap offline preflight (HOLD)

This is **candidate-only, non-executing preparation**. It does not adopt Terraform
1.16.7 / AWS Provider 6.70.0, enable maintenance/recovery, perform Terraform
validation, authenticate AWS, read State, or authorize Plan/Apply.

## Separation of execution contracts

- Existing formal and historical bootstrap maintenance/recovery paths remain
  unchanged at Terraform **1.14.9**, including their old approval and receipt
  schemas. The new module is not imported by either execution controller.
- The proposed candidate execution namespace is
  `p4-bootstrap-candidate-1.16.7-aws-6.70.0-linux_amd64-v2`.
  Terraform **1.17.0** is offline qualification only, not an approved candidate
  bootstrap runtime.
- `backend/skills/p4/candidate_bootstrap_preflight.py` accepts exact v2
  synthetic/local manifests, six HCL requirements and six provider locks,
  Terraform version JSON, a binary digest, State identity, a separate approval,
  and a NEW attempt journal. Apply/recovery additionally require a same-namespace
  saved Plan manifest, matching binary bytes and distinct Plan approval.
- Mismatched versions, provider selections, platform, namespace, identity,
  approval, plan hashes, missing fields, extra fields, and FAILED/UNKNOWN
  attempt states fail closed.
- Successful return means only
  `OFFLINE_CANDIDATE_PREFLIGHT_ONLY`, `authorized: false`, `aws_operations: 0`.
  There is deliberately **no CLI main, Terraform subprocess, SDK client,
  backend initialization or execution path**.

## Unproven security and operational properties

This pure validator cannot attest that JSON was genuinely emitted by a
specific Terraform binary; that the binary checksum came from an official
source; that official provider package hashes cover the local platform; that
a saved Plan was created with the claimed CLI; that any hash/approval is
signed, fresh or unforgeable; that the journal is atomically durable; or that
real State/upgraders/defaults/API Gateway/SNS identities are compatible.
In particular, a matching synthetic Plan manifest **does not prove** the
saved binary's producing runtime or allow it to be applied.

The HCL version-token checks are not Terraform syntax validation. Any future
real execution controller must independently implement **all** of these gates
before AWS authentication and before attempt consumption:

1. Immutable Git/source/review identity and exact candidate source bytes.
2. Official checksums, Terraform version/platform and provider installation
   checks; sterile `init -backend=false` and `validate` on a disposable
   checkout, with no credentials, before SDK access.
3. Authenticated, expiry-bound, one-use approvals tied to the entire CLI,
   Provider, platform, HCL, original State version/lineage/serial/hash,
   immutable Plan bytes and fresh review evidence.
4. Separate idempotent failure/UNKNOWN journals and explicit no-retry rules
   that survive process crash and partial success.
5. Independent operating/security review and real AWS/State/provider
   readback after **separate authorization**. Candidate-only checks do not
   satisfy the HOLD-release or Apply authorization boundary.

All remote State access, formal Plan/Apply, AWS, paid inference, Environment
readiness and PR #43 merge remain **HOLD**. Do not invoke historical
controllers with candidate evidence or reuse historical Plan binaries,
approvals, receipts, or ledgers.
