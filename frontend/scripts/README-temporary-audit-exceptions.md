# Temporary frontend development dependency audit exception (Issue #92)

Status: **risk accepted temporarily**, **not remediated**.

## Why

On 2026-11-01 the frontend dev-inclusive `npm audit` reports 21 moderate affected packages, derived from exactly two advisories:

- [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) — `minimatch` denial of service
- [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) — `glob` cancellation bypass/continued traversal

These are currently in the ESLint/Storybook development-tool dependency graph. The production-only command `npm audit --omit=dev --audit-level=low` **must remain an independent blocking check**. This is an exception for the two named GHSA IDs only, not an exemption for all moderate issues.

## Enforcement

`node scripts/audit-known-exceptions.mjs` executes unmodified `npm audit --include=dev --audit-level=low --json`. It parses *every* direct advisory and transitive meta-vulnerability, and rejects:

- Any unknown advisory ID, including a new moderate affecting `minimatch` or `glob`
- Any low/info/high/critical vulnerability, severity escalation, or ungrounded affected package
- Unexpected npm process status, failed registry audit, missing/invalid JSON, malformed or contradictory counts
- These two existing advisories on or after **2026-11-15 00:00 UTC (09:00 JST)**

An entirely clean audit continues to pass after the review deadline. All exceptional results are visible in CI logs, and `node --test scripts/audit-known-exceptions.test.mjs` runs before the audit policy in CI.

**The user-approved temporary exception does not authorize** removing security scans, disabling production dependency auditing, altering protected rules, dependency overrides of incompatible major versions, or claiming the upstream vulnerabilities are fixed.

## Reassessment

By 2026-11-15, recheck official upstream package releases and advisories, then either remove the exception after verified compatible remediation or obtain an explicit new dated risk decision. Failure to make a decision must fail CI.

This decision alone does **not** authorize public release. AWS/Cognito/Claude live E2E, deployment, security, and performance gates are separate.
