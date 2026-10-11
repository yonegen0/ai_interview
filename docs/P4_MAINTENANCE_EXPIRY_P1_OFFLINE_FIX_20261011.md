# Maintenance Apply expiry P1 offline fix (2026-10-11)

Base: `9cbdc06b8791a0237b1b48564df59d2c4469a697`.
Review finding: R4 in `CODE_REVIEW_SINCE_6F211F3_20261011.md`.

An approval valid at execute entry could expire while actor, State, 32-resource,
backend, saved-plan and binding reads completed. The old maintenance path still
started the IAM/State write process after that expiry.

After final saved evidence/resource verification, the controller now rereads the
same approval file with the originally approved SHA-256, requires identical raw
bytes and parsed values, and revalidates scope and expiry immediately before
claiming apply-started. It repeats that check after durable journal creation and
immediately before invoking Terraform. Expiry or tampering prevents the process.
If expiry occurs during journal persistence, the attempt marker remains and a
replay is rejected; no journal is removed or repaired.

The synthetic orchestration regressions advance the clock during State reads or
journal creation, and mutate the descriptor during reads. Each path observes
zero mock apply calls. Existing partial failure, timeout, binding, State and
single-attempt regression cases remain active.

Targeted offline suite: 98 PASS, 1 SKIP (Windows symlink privilege); Ruff and Git
whitespace checks PASS. Fixtures prohibit socket/SDK transport. A dedicated
evidence-directory launcher only permits inherited ACLs for synthetic pytest
fixture directories; implementation privacy gates remain unchanged.

## Existing recovery binding impact

This independent fix changes `bootstrap_maintenance.py`, one of the source files
hashed by the existing formal recovery audit. It must not be substituted into
the already recovered fixed-revision execution source, nor may its hash be
written into old journals/bindings. Main integration changes remote main and
would affect the existing revision Gate unless an independently reviewed
controller-execution strategy preserves that Gate. Keep this PR independent
pending that decision. No live Apply or recovery rerun is authorized here.

No AWS connection, Terraform plan/apply/destroy, real IAM/State mutation, original
Plan, journal or schema 2 binding modification occurred.
