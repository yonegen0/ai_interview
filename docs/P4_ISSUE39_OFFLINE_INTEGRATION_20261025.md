# Issue #39 offline integration and closure evidence

## Scope and authorization

The user's 2026-10-25 instruction authorizes ordinary integration/merge of the
offline, non-authorizing code after independent review and genuine required CI.
It supersedes older PR #45–#49 merge HOLD statements **only for this scope**.
It does not release operational HOLD, adopt a candidate runtime, grant execution
authority or authorize AWS/remote State/formal Plan/Apply/deployment/paid AI.
Formal Terraform remains 1.14.9. PR #43 stays Draft/HOLD. Production prerequisites
are recorded in [Issue #50](https://github.com/yonegen0/ai_interview/issues/50).
Older evidence documents remain historical records, not current merge policy.

The integration starts from main `aa5952930160c7a6bb91765bd0bfd542500becde`.
Its staged tree was compared with PR #49 `447d7db8ebee135497136a5c40dcc13111c03835`:
the complete 41-file final stack delta was identical before the fixes below.
No obsolete stack ancestry or PR #43 adoption changes were imported. The original
checkout and its unrelated uncommitted changes remain untouched.

## ZIP discrepancy: confirmed cause and repair

The retained local ZIP is 47,007,832 bytes, SHA256
`197884f1980a9a3e6fde8fc651024795b9b3a5921bf7cf07d2ce5ee296970673`.
PR #49 CI run 40194090884/job 121171135950 recorded 46,998,689 bytes, SHA256
`2221a5edbaa55f6bc6b6f16845b63d5e8b4b94739d81d4db41c4073ba3e767ca`.
That old CI run retained no artifact or entry inventory, so its original ZIP
cannot be recovered from Actions. Its hash/size remain log evidence.

An entry-by-entry comparison against raw Git blob bytes found **52 application
source files containing CRLF instead of LF, exactly 9,143 extra bytes**.
The local Windows Git configuration has `core.autocrlf=true`; even its original
`git archive` exported CRLF. Merely copying that archive into Linux did not fix
the inputs. Fresh uv 0.13.5/Python 3.14.9 staging using the exact CI
`x86_64-manylinux_2_34`, binary-only, hash-required install reproduced the local
hash when supplied that source. Re-exporting the same commit with
`git -c core.autocrlf=false archive` and the same dependencies reproduced the
**exact existing CI size and hash above**, without changing an expected digest.

The discrepancy is source text conversion, not a wheel, dependency version,
installer RECORD, metadata, compression or UNIX-attribute difference. Both ZIPs
use stored entries with fixed timestamp, sorting and UNIX attributes; their
dependency entries are identical. Python/JSON semantics are unchanged by these
line endings, but package byte identity matters for approval/hash bindings.

The minimal repair is `.gitattributes` scoped to
`backend/src/interview_backend/** text eol=lf`. It pins checkout/archive inputs
without altering dependency bytes or rewriting the ZIP builder. New CI retains
entry path/size/SHA256/timestamp/attributes/compression and its package manifest
for direct comparison with the final local ZIP. Only public package comparison
metadata is uploaded, never State, Plan, credentials or private evidence.

## Independent security review and concrete correction

A separate reviewer inspected all 16 files in `1a683f3..447d7db`, implementation,
tests, dependency/CI delta and underlying contracts. It found no concrete P0/P1
and one P2: replacing a tracked Terraform source with a FIFO blocked the source
snapshot reader before its regular-file check. `O_NONBLOCK` was added to that
reader, retaining `O_NOFOLLOW` and the `fstat` rejection. No authorization gate
or error expectation was relaxed.

The independent reproduction timed out before the fix. The committed regression
also failed before the fix with a five-second subprocess timeout; after the
one-line repair, snapshot/controller tests passed **44/44**. The reviewer ran
**72 focused Windows tests** and **80 Linux PR #49 tests** successfully using a
separate exact-SHA archive, empty environment/HOME and `unshare -n`. Review
independence is a separate agent/source directory, with the same physical host
and pinned runtime libraries; it is not independent hardware or AWS validation.

Reviewed properties include SQLite atomic IDs/CAS/tombstones/history/floor/UNKNOWN,
signature-versus-authority distinctions, producer/Plan/source bindings,
symlink/TOCTOU limits, fixed probe commands/network isolation, dangerous package
content exclusion and v2/v3 compatibility. All successful local results remain
`authorized=False`. Same-host DB+floor rollback, cross-host authority, enrollment,
clock, real producer/State and actual loaded-toolchain identity remain operational
HOLDs in #50; they are not claimed solved by this offline code.

## Issue acceptance mapping

| Original acceptance criterion | Offline evidence / disposition |
| --- | --- |
| CLI/Provider/version/lock/workflow inventory, six scopes | Existing toolchain migration inventory and six-scope qualification; final Actions must run both 1.16.7 and 1.17.0 with Provider 6.70.0. Formal pins remain unchanged. |
| Separate legacy evidence from new execution contract | Existing legacy compatibility guards plus candidate v2/v3/v4 pure contracts; old approvals/plans never gain execution authority. |
| Official-tool-generated candidate locks | Disposable migration script generates six lockfiles using official candidate CLI/checksums; PR #43 retains adoption-only tracked locks/HOLD. No hand-edited hashes. |
| fmt/init-backend-disabled/validate/Mock across six scopes | Existing normal 1.14.9 and candidate qualification workflows, credential-free disposable roots; no remote backend or formal Plan/Apply. |
| Old/new synthetic saved-plan/JSON consumers | Existing compatibility suites and new source/producer/approval/Plan byte mismatch tests; legacy binaries cannot authorize candidate Apply. |
| IAM/OIDC/State/UNKNOWN/approval/merge negatives | Existing compatibility/guard suites and stack negative tests; no dispatch/executor added. |
| Advisory/setup pins/dependency audit | Prior release-impact inventory, unchanged immutable Action pins, uv-generated crypto lock; final dependency-audit Actions required. Candidate success does not remediate the still-formal runtime by itself. |
| Independent review and genuine required Actions | Independent review and FIFO correction above; exact final PR and post-merge run IDs/results must be recorded in the integration PR and Issue #39 before closing. |

The issue body is preserved. Operational adoption requirements are explicitly
separate; no unperformed operational item should be checked as completed.
Closure requires ordinary merge, matching-commit required CI and successful main
Actions. CI completion and main SHA are recorded in GitHub rather than guessed
in this pre-merge source document.

## Official references

- [Git text/eol attributes](https://git-scm.com/docs/gitattributes)
- [Python 3.14 os flags](https://docs.python.org/3.14/library/os.html#os.O_NONBLOCK)
- Existing PR #49 evidence documents retain cryptography/SQLite/Terraform primary
  references and exact downloaded toolchain digests.
