# New main Artifact upload-only readiness — 2026-10-09

PR #1 was merged as a merge commit at `f6ad017477826a27965e72a30c5fde4d80069606`.
Its new local Artifact has 483 tracked source blobs, 39 application blobs and
2377 ZIP members. The existing upload-only driver deliberately pins the old
Artifact's 287 source blobs, 2366 ZIP members and dated validation paths.
Its checked-in approval also names an older source/hash/size. Reusing or
rewriting that approval is outside the PR #1 merge authorization.

This branch adds a schema 2 path for a separately approved local descriptor.
Schema 1 retains its exact historical validation paths and counts. No existing
approval, workflow, IAM, WIF, runtime, dependency or application file changes.

Schema 2 pins source and ZIP inventory counts in the approved descriptor. It
compares the source count with the immutable Git revision, the ZIP count with
the actual duplicate-free archive, and each application member with its Git
blob. It retains manifest/provenance/evidence digests, runtime/architecture,
locked dependency digest, official-source/builder evidence, security status,
unknown-findings rejection and the exact application file-set guard. It also
requires a second ZIP in the hashed evidence and verifies that its digest
equals the approved first ZIP.

New evidence paths are `validation/final.private.json` and
`validation/baseline.private.json`; they are mandatory entries in the pinned
provenance. Counts cannot be supplied by evidence alone. A mismatched approval,
actual Git inventory, actual ZIP inventory, second build or application blob
still stops before any AWS client.

The one-job runner may set `P4_UPLOAD_APPROVAL_PATH` to an absolute local
descriptor and `P4_APPROVED_ARTIFACT_APPROVAL_SHA256` to its separately reviewed
SHA-256. This optional descriptor must be schema 2, have `approved: true` and
match the exact digest. A preparation draft has `approved: false` and is
rejected. The default remains the unchanged historical schema 1 file. Local
descriptor paths must satisfy the existing no-symlink/no-junction file guard.
Schema 2 in the default repository file is rejected; it cannot bypass the
separate local descriptor digest and explicit approval check.

GitHub main/dev/run/attempt/actor checks, all OIDC claims, role/bucket constraints,
read-only preflight, one PutObject, `IfNoneMatch=*`, durable attempt marker,
encryption/checksum/metadata, exact VersionId readback, version inventory and
no-retry behavior are unchanged. No Terraform/build import is introduced into
the transfer driver. This branch performs no upload or workflow dispatch.

Offline verification covers both schemas, changed evidence, actual source and
ZIP count mismatch, application blob mismatch, reproduction mismatch, missing
or changed descriptor hash, and unapproved descriptors. The real new local ZIP
was checked against all 39 Git blobs with socket access forbidden; its legacy
approval and `approved: false` preparation descriptor were both rejected.

Windows verification: full offline Backend regression 1328 passed / 57
deselected; after the final descriptor-bypass guard and regression case, all
67 upload tests passed (55 historical + 12 new). Ruff check/format passed for
130 files. Latest-commit GitHub CI is the final full-regression check.

Private payloads and Artifact evidence remain outside Git. This branch is a
code review proposal, not approval to merge it, use the runner or write AWS.
After an explicitly approved merge, bind a clean latest-main Artifact and all
validation/provenance to that resulting main SHA. Then present a separate
upload-only authorization: exact source/ZIP/size/manifest/provenance/descriptor
digests, Account/Region/bucket, immutable
`lambda/<source_sha>/<real_run_id>/1/app.zip`, one attempt and expected storage
cost. The real workflow run ID is checked after the authorized dispatch.
No Plan/apply/IAM/Enablement/Closure or paid AI permission is implied.
