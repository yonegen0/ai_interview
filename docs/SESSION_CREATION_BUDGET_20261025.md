# Session creation budget (2026-10-25)

## Security objective

An invited authenticated user could otherwise create unbounded retained Sessions
and IdempotencyRecords with fresh idempotency keys. Shared API Gateway throttling
is not a per-user storage or billing guard.

## API contract

- Up to **60 new Sessions per authenticated owner per UTC calendar month**.
- Replaying an existing matching idempotency key returns its original 201 response
  without consuming another quota unit, including after a UTC month change.
- A reused key with a changed payload remains HTTP 409 `IDEMPOTENCY_CONFLICT`.
- New keys beyond the monthly cap return HTTP 429 `SESSION_CREATION_LIMIT`;
  that unsuccessful key can be reused after the next UTC month starts.
- Owners have independent limits. Prior Session/Attempt/history records and
  historical idempotency replies are never deleted or assigned new TTLs.
- Counters begin with the deployed feature; **older retained Sessions are not
  retroactively counted**. No migration or table scan is performed.
- This is a *creation-frequency cap*, not a total lifetime-storage quota.

## Atomic storage design

A dedicated `SessionCreationBudget` record is keyed by authenticated owner and
a deterministic UUIDv5 for the UTC month; it is separate from AI/provider budgets.
A successful POST /sessions updates the budget, creates the Session and stores
the idempotency reply within one conditional DynamoDB transaction.
Concurrent writers must satisfy the budget record revision CAS check, and retries
must re-read the updated count. On transaction failure, none of the three records
is partially committed. MemoryRepository provides equivalent copy-on-write
serialization for offline tests. The new item has no work index and no TTL.

## Operational tradeoffs

- The server-side limit is fixed at 60, not controlled by request fields.
- Reaching the limit blocks legitimate new sessions until next UTC month,
  although old sessions remain accessible. No Retry-After is sent.
- DynamoDB quota reads and CAS writes add transaction costs and contention.
  Actual AWS transaction/failure tests require a separate explicit authorization.
- Exhausted SDK retry budgets still produce the existing safe storage error,
  never a successful quota bypass.
- The underlying DynamoDB table schema, IAM policies, Terraform remote state,
  Bedrock budgets and existing Session history remain unchanged.

References:
- [DynamoDB TransactWriteItems API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)
- [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
