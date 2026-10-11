# Bootstrap historical audit and post-Apply integration

Completed recovery and Apply records remain bound to their original full Git
revisions, code manifests, saved Plan, approvals, binding and journals. Preserve
those bytes and the archived clean execution worktrees. A later main revision
does not become the revision audited by the historical approval.

After a successful Apply the durable namespace contains Apply start and completion
records. The saved Plan is consumed even if its approval has not expired. Never
remove those records, change runs to retry, or rebind the old approval to new code.
The current canonical State identity must be checked under a separate approval
before any new operation; the old pre-Apply State is historical evidence only.

The recovered controller requires its reviewed topic branch and the original
clean/remote main revision. Main integration therefore causes the old execution
gate to reject. A changed maintenance dependency also fails the original audit
code manifest. These are intentional fail-closed results, not permission to relax
the gates. Historical success is verified offline from the immutable source,
binding, journals and readbacks; it is not re-executed or claimed for new main.

The maintenance expiry rechecks and integer-only approval schema validation add
rejections without adding IAM permissions, State operations or a retry path.
Valid integer-schema approvals retain their existing behavior. Historical
descriptors are not edited to adopt the new validation code.

Future main execution needs a separately reviewed revision/code contract and
explicitly scoped authorization. Do not reuse a recovered Plan or substitute
new source hashes into its historical binding. Real AWS access, saved Plan
generation, Apply, Enablement and deployment remain separate approval boundaries.
