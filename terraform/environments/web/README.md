# Private static frontend

This separate root implements the existing Private S3 + CloudFront OAC architecture.
It uses `web/terraform.tfstate`, separate from bootstrap and service State. Both the
distribution and service API remain closed by default. No custom domain, hosted
zone, custom KMS key, paid runner, fixed-capacity server or logging bucket is added.

Use the trusted existing state bucket/account/independent development profile.
Generate a fresh saved Plan and independently inspect it before applying that exact
binary. Initial changes should only create this dedicated hosting stack; stop any
unexpected deletion/replacement, permission expansion or State/key mismatch.
Neither this README nor mock tests establish an actual deployed frontend.

After application deployment, build the real static export using the actual
Cognito/API public settings. Keep MSW disabled and exclude `.env`, source maps,
tokens, state, private artifacts and `mockServiceWorker.js` from uploaded assets.
The bucket holds static frontend files only. Match the service CORS origin to the
generated HTTPS origin; Cognito client identifiers are public configuration, not
credentials. Verify Email OTP, ownership, STAR/coaching/history/retry and performance
before enabling public delivery. Retain normal rollback assets and use controlled
cache invalidation for an updated export.

Route lookup matches the existing `trailingSlash: true` export: `/interview` and
`/interview/` map to `/interview/index.html`; file paths stay unchanged. Missing
objects serve the exported 404 page with a 404 response, not a successful SPA fallback.

CloudFront/S3/function requests, transfer and storage are usage-based. No promise
of unconditional free billing is made. Check applicable current allowances and
actual asset size before upload; keep the existing budgets unchanged. Noncurrent
asset versions expire after seven days; incomplete multipart uploads expire after
one day. Distribution provisioning can take approximately fifteen minutes.

## Build and upload using standard CLI commands

Run from the repository root after the service and hosting saved Plans have been
applied and read back. `$ServiceManifestPath` and `$WebOutputPath` refer to private
JSON copies of the actual `manifest` and `frontend` Terraform output values;
`$AwsProfile` is the verified existing development principal. Use the hosting
bucket and distribution from that readback, never the State/artifact buckets.
The principal must already be authorized for these uploads and invalidation;
these commands do not change IAM or add a deployment workflow.

`NEXT_PUBLIC_` values are embedded at build time. Set them before building from
the reviewed source; changing an environment variable after upload does not
reconfigure an existing export. The service CORS allowlist must contain the exact
`$web.origin`. The Cognito client must be the public browser client without a
client secret.

```powershell
$service = Get-Content -LiteralPath $ServiceManifestPath -Raw | ConvertFrom-Json
$web = Get-Content -LiteralPath $WebOutputPath -Raw | ConvertFrom-Json
$env:NEXT_PUBLIC_API_BASE_URL = $service.api_endpoint
$env:NEXT_PUBLIC_COGNITO_REGION = "ap-northeast-1"
$env:NEXT_PUBLIC_COGNITO_USER_POOL_ID = $service.user_pool_id
$env:NEXT_PUBLIC_COGNITO_CLIENT_ID = $service.client_id
$env:NEXT_PUBLIC_MSW_ENABLED = "false"

Push-Location frontend
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "Frontend dependency install failed" }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "Production export failed" }
} finally {
  Pop-Location
}
```

Use only `frontend/out`, never `out-mock` or `storybook-static`. The production
build removes the MSW worker. Inspect the export for unintended files and record
its source SHA, public settings, total size and file hashes before uploading.
The excludes below are additional protection for files that must not be served.
Keep the existing S3 public-access blocks and OAC policy; do not add a public ACL.

Upload content-hashed Next assets first, then the HTML and other short-lived
files. Run both commands with `--dryrun` first; after checking the destinations and
file list, run the same commands without that option. Do not add `--delete`:
older hashed assets remain available to pages already open in a browser.

```powershell
aws s3 sync frontend/out/_next/static "s3://$($web.bucket_name)/_next/static" --profile $AwsProfile --region ap-northeast-1 --no-follow-symlinks --sse AES256 --cache-control "public,max-age=31536000,immutable" --exclude "*.map" --exclude "*.env*" --exclude "*mockServiceWorker.js" --dryrun
if ($LASTEXITCODE -ne 0) { throw "Next asset upload failed" }

aws s3 sync frontend/out "s3://$($web.bucket_name)" --profile $AwsProfile --region ap-northeast-1 --no-follow-symlinks --sse AES256 --cache-control "public,max-age=300" --exclude "_next/static/*" --exclude "*.map" --exclude "*.env*" --exclude "*mockServiceWorker.js" --dryrun
if ($LASTEXITCODE -ne 0) { throw "Frontend file upload failed" }
```

After both uploads succeed, invalidate the exact distribution once and wait for
that invalidation to complete before checking the updated pages. A quoted `/*`
covers the rewritten routes and cached HTML. Record the returned invalidation ID;
an uncertain response is not permission to submit a new invalidation.

```powershell
$invalidation = aws cloudfront create-invalidation --distribution-id $web.distribution_id --paths "/*" --profile $AwsProfile --no-cli-pager --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "CloudFront invalidation result unknown" }
aws cloudfront wait invalidation-completed --distribution-id $web.distribution_id --id $invalidation.Invalidation.Id --profile $AwsProfile
if ($LASTEXITCODE -ne 0) { throw "CloudFront invalidation is not confirmed complete" }
```

This upload does not change `enabled`. Use the existing saved-Plan process for
limited live validation and eventual release; a disabled distribution cannot be
used for browser E2E. Verify the deployed routes, missing-page 404, MIME/cache and
security headers, MSW absence and the real authenticated flows. Existing
`npm run test:e2e` uses localhost/MSW and is not a live AWS acceptance test.

Command references: [Next static export](https://nextjs.org/docs/app/guides/static-exports),
[Next public environment variables](https://nextjs.org/docs/app/guides/environment-variables),
[AWS CLI S3 sync](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html),
[CloudFront versioned files](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/UpdatingExistingObjects.html)
and [CloudFront invalidation](https://docs.aws.amazon.com/cli/latest/reference/cloudfront/create-invalidation.html).
