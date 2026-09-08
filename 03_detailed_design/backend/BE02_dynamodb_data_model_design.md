---
document_id: DD-BE-002
title: "Backend詳細設計 BE02 DynamoDBデータモデル設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. Table

Logical name:
`interview-training`

Billing:
On-Demand

Primary:
- PK string
- SK string

# 2. PROFILE

```text
PK = USER#{sub}
SK = PROFILE
```

```json
{
  "PK": "USER#abc",
  "SK": "PROFILE",
  "userId": "abc",
  "name": "山田 太郎",
  "email": "user@example.com",
  "status": "ACTIVE",
  "practiceCount": 34,
  "favoriteCount": 5,
  "lastPracticedAt": "2026-09-08T03:30:00.000Z",
  "createdAt": "2026-09-01T01:00:00.000Z",
  "updatedAt": "2026-09-08T03:30:00.000Z",
  "GSI1PK": "ENTITY#USER",
  "GSI1SK": "2026-09-01T01:00:00.000Z#abc"
}
```

`role`は認可正データにしない。

# 3. PRACTICE

```text
PK = USER#{sub}
SK = PRACTICE#{createdAt}#{practiceId}
```

Attributes:
- practiceId
- questionId
- questionBankVersion
- category
- question snapshot
- answer
- rating
- goodPoint
- improvement
- improvedAnswer
- favorite
- modelId
- inferenceTargetId
- promptVersion
- createdAt

Favorite=true時のみ:
```text
GSI2PK = USER#{sub}#FAVORITE
GSI2SK = {createdAt}#{practiceId}
```

# 4. REQUEST

practiceId lookup + idempotency。

```text
PK = USER#{sub}
SK = REQUEST#{practiceId}
```

```json
{
  "status": "PROCESSING",
  "practiceId": "uuid",
  "practiceSk": null,
  "usageDate": "2026-09-08",
  "startedAt": "...",
  "completedAt": null,
  "errorCode": null
}
```

初回作成は単独Putではなく、`USAGE.aiInvocationCount`加算と同じ`TransactWriteItems`に含める。
REQUEST Put条件:
`attribute_not_exists(PK) AND attribute_not_exists(SK)`

COMPLETED:
- practiceSkを保存
- duplicate requestでPractice itemへ解決

FAILED:
- errorCode保存
- 同一IDを自動再Bedrockしない

# 5. USAGE

JST日付をキー化。

```text
PK = USER#{sub}
SK = USAGE#{YYYY-MM-DD}
```

```json
{
  "aiInvocationCount": 12,
  "completedPracticeCount": 11,
  "updatedAt": "..."
}
```

AI開始時はREQUEST作成と同一TransactionでAtomic Updateする。

概念式:
```text
SET aiInvocationCount = if_not_exists(aiInvocationCount, 0) + 1
Condition = attribute_not_exists(aiInvocationCount)
            OR aiInvocationCount < DAILY_FEEDBACK_LIMIT
```

TransactionのREQUEST Put条件またはUSAGE上限条件のどちらかが失敗した場合、両方をrollbackしBedrockを呼び出さない。

コスト制御の`aiInvocationCount`とUI実績`completedPracticeCount`を分離する。

# 6. GSI1 Admin Users

```text
GSI1PK = ENTITY#USER
GSI1SK = createdAt#userId
```

PROFILEのみ設定するSparse Index。

# 7. GSI2 Favorite

```text
GSI2PK = USER#sub#FAVORITE
GSI2SK = createdAt#practiceId
```

favorite=trueのPRACTICEだけ設定。

# 8. History Query

```text
PK = USER#sub
SK begins_with "PRACTICE#"
ScanIndexForward = false
```

CursorはLastEvaluatedKeyをOpaque化。

# 9. practiceId Lookup

PATCH Favorite:
1. Get `REQUEST#practiceId`
2. `practiceSk`取得
3. 対象PRACTICEをUpdate

これによりhistoryのsort keyとID lookupを両立する。

# 10. Practice保存Transaction

## 10.1 AI開始Transaction

Bedrock前:
1. Put REQUEST -> PROCESSING（request不存在Condition）
2. Update USAGE aiInvocationCount +1（日次上限Condition）

`TransactWriteItems`を使用し、冪等ロックとコストカウントを原子的にする。

## 10.2 AI成功後Transaction

1. Put PRACTICE
2. Update REQUEST -> COMPLETED + practiceSk
3. Update PROFILE practiceCount +1, lastPracticedAt
4. Update USAGE completedPracticeCount +1

`TransactWriteItems`を使用する。

# 11. Favorite Transaction

1. REQUESTからpracticeSk解決
2. PRACTICE current favorite確認
3. Condition付きUpdate
4. PROFILE favoriteCount ±1

同じ値の再送ではCount変更しない。

# 12. Consistency

- REQUEST lock: Strongly consistent Getを利用可
- History: Eventually consistentで可
- Profile count: Transaction後の表示は必要に応じてrefetch

# 13. Time

保存:
UTC ISO 8601

Daily usage判定:
Asia/Tokyoの日付

# 14. TTL

MVP:
- PRACTICEはRetention Policy確定までTTLなし
- REQUEST completed/failedは将来TTL設定可
- PROCESSINGを安易に自動削除しない

# 15. PII

email/name/answerを保存するため、IAM権限をFunction単位に制限する。
DynamoDB Encryption at Restを使用する。

---

## 参照公式ドキュメント

- [DynamoDB - On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [DynamoDB - Maximum throughput for on-demand tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

