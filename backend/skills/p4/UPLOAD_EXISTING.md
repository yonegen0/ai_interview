# Upload an approved existing Lambda ZIP

`p4-deploy.yml` has an independent `upload-existing` operation. It skips the
Backend, offline, and deployment jobs. It does not build a ZIP or invoke
Terraform, State locking, plan/apply, or any application resource mutation.
The existing `plan` and `apply` operations retain their previous behavior.

The artifact source revision and the workflow execution revision are distinct.
The immutable source revision, ZIP size/hash, manifest hash, and a digest of the
private provenance record are pinned in `upload_existing.approval.json`.
The provenance record lists digests of the existing local validation evidence.
The driver checks these files and compares every application member in the ZIP
with the original source revision's raw Git blobs. It never imports ZIP code.

## Prepared local runner

Use a freshly provisioned **ephemeral, one-job** Windows x64 runner with a unique
`p4-upload-existing-...` label and no default labels. Do not install it as a
service. The ZIP and private receipt stay on the existing local filesystem;
neither a public release nor a staging S3 object is needed.

Queue the authorized workflow dispatch once, obtain its real run ID, verify its
revision, then start the matching runner with these process-local settings:

- `P4_UPLOAD_PYTHON`: existing prepared Python 3.14 executable with boto3.
- `P4_UPLOAD_SOURCE_DIR`: directory containing the unchanged `app.zip`,
  `package.json`, and original validation evidence.
- `P4_UPLOAD_PROVENANCE`: pinned private provenance record.
- `P4_UPLOAD_RECEIPT_DIR`: fresh durable local private directory.
- `P4_UPLOAD_READ_PROFILE`: existing SSO profile for read-only preflight.
- `P4_APPROVED_EXECUTION_SHA`, `P4_APPROVED_RUN_ID`: verified values from this
  dispatch. The driver accepts only attempt 1.
- `P4_APPROVED_RUNNER_NAME`, `P4_APPROVED_RUNNER_LABEL`: this one-job runner.

Only trusted, reviewed code may run on this prepared runner. Use no default
runner labels, start it only for the already queued approved job, and verify
automatic deregistration after that job. Credentials and OIDC tokens must not
be included in receipts or console output.

## AWS boundary

The existing SSO profile is used for STS identity, Bucket settings, and exact-Key
version-history reads. The artifact CI role lacks lambda-prefix List grants;
this separate read-only session avoids changing IAM. The sole PutObject and
the version-pinned GetObject use short-lived credentials obtained through the
actual job's OIDC token and `ai-interview-ci-artifact` role.

The driver verifies GitHub run metadata and main/dev controls, then OIDC issuer,
audience, exact subject, repository, environment, ref, event, both workflow
claims, run ID/attempt, and actor. AWS STS verifies the token signature.

Key: `lambda/<artifact_source_sha>/<run_id>/<attempt>/app.zip`.

Before the only PutObject, all matching versions and delete markers must be
absent. An exclusive `attempt.private.json` is flushed to disk. The S3 client
uses `total_max_attempts=1`. The Put supplies `IfNoneMatch="*"`, AES256, expected
owner, SHA-256 checksum, and identity metadata. No S3 sidecar is written.

Success requires a non-null response VersionId, GetObject of that exact version,
matching size/SHA-256/encryption/identity metadata, and exactly one version at the
Key. `receipt.private.json` and `retrieved-app.zip` are stored locally.

If an attempt marker exists, do not rerun or remove it. Investigate the same Key
and its versions with read-only APIs. A failed or uncertain write never causes
an automatic second PutObject. A new workflow attempt is not a retry mechanism.

## Verification and publication

Run the upload unit tests, relevant P4 unit tests, the existing private policy
tests, Python lint, workflow static analysis, and review the diff before push.
For an upload-only authorization, use `[skip ci]` in the commit message to avoid
triggering the ordinary push-based build/Terraform workflows; dispatch the
upload operation explicitly once. Do not bypass branch protections if push is
rejected. A successful upload receipt is not a saved Terraform plan envelope.
