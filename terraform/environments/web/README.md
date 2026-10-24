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
