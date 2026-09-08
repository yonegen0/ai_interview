---
document_id: DD-BE-005
title: "Backend詳細設計 BE05 冪等性・利用制限・エラー・ログ設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 目的

Bedrockの重複課金、API乱用、障害時の不整合、PIIログ漏えいを抑える。

# 2. practiceId

FrontendでUUID v4を生成する。
`practiceId`は「1回の論理送信intent」を識別する。

ルール:
- 初回送信: 新しいID
- HTTP timeout / response lost /一時的network failure後のTransport Retry: **同一ID**
- TanStack Query等によるAI POST自動retry: 無効
- Backendが`FAILED`を確定し、ユーザーが新しい練習としてやり直す: **新しいID**

同一回答を同じ意図で再送するだけなのに新IDへ変えない。

# 3. Idempotency Lock

Bedrock前に単独Putせず、日次利用回数更新と同じ`TransactWriteItems`で開始する。

```text
TransactWriteItems
├─ Put REQUEST#practiceId
│    status = PROCESSING
│    Condition = attribute_not_exists(PK) AND attribute_not_exists(SK)
└─ Update USAGE#YYYY-MM-DD
     aiInvocationCount += 1
     Condition = DAILY_FEEDBACK_LIMIT未満
```

Transaction成功したrequestだけBedrockへ進む。

既存REQUESTを事前/競合後に取得:
- COMPLETED: 保存済みresultを返す
- PROCESSING: `409 PRACTICE_PROCESSING`
- FAILED: `409 PRACTICE_FAILED`

Duplicate REQUESTでTransactionが失敗した場合、USAGE加算もrollbackされる。

# 4. External Call Failure Window

Bedrock成功後、DynamoDB保存前にLambdaが異常終了する可能性はゼロにできない。

コスト優先方針:
- 同一`practiceId`では再Bedrockしない
- REQUESTがPROCESSINGならTransport RetryでもBedrockを再実行しない
- 正常保存済みならCOMPLETED結果を再返却する
- PROCESSINGがfeedback Lambda timeout + safety marginを超えて残る場合は運用/Backendロジックで`FAILED`へ収束できるよう、`startedAt`を保存する
- `FAILED`確定後にユーザーが再挑戦する場合は新`practiceId`

これによりレスポンスロストによる二重課金を抑えつつ、永続PROCESSINGからの回復余地を残す。

# 5. Daily Limit

JST日付Key:
`USAGE#YYYY-MM-DD`

Bedrock呼び出し前にREQUEST lockと同一TransactionでAtomic Updateする。

概念式:
```text
SET aiInvocationCount = if_not_exists(aiInvocationCount, :zero) + :one
Condition = attribute_not_exists(aiInvocationCount)
            OR aiInvocationCount < :limit
```

上限条件に失敗した場合はREQUEST Putも成立しない。
Bedrockは呼び出さず、`429 DAILY_LIMIT_EXCEEDED`を返す。

# 6. Usage vs Practice

- aiInvocationCount: コスト管理
- completedPracticeCount: 成功した練習
- PROFILE.practiceCount: UX集計

分離する。

# 7. API Throttling

API Gateway route throttlingは急激なburst対策。
ユーザー単位Daily limitの代替にはしない。

# 8. Lambda Reserved Concurrency

feedback Lambdaに上限を設定可能。
数値はTBD。

目的:
- Bedrock同時呼び出し上限
- runaway防止
- 他Functionへの影響分離

# 9. Validation Error

Clientへ安全な一般化message。

ログへ入力本文を出さない。

# 10. Logging Schema

```json
{
  "requestId": "...",
  "route": "POST /v1/practices",
  "userId": "sub-or-hash",
  "status": 201,
  "latencyMs": 1234,
  "bedrockLatencyMs": 900,
  "model": "...",
  "promptVersion": "feedback-v1",
  "errorType": null
}
```

禁止:
- answer
- improvedAnswer
- email
- name
- OTP
- JWT
- Authorization header

# 11. Metrics

Custom metric候補:
- FeedbackSuccess
- FeedbackFailure
- DailyLimitExceeded
- AIInvalidResponse
- IdempotencyConflict
- BedrockLatency

# 12. Error Mapping

AWS SDK exceptionを直接返さない。

内部:
- CognitoError
- DynamoDbError
- BedrockError
- ValidationError

外部:
- 安定したApiError code

# 13. Request ID

API Gateway request IDまたはLambda context IDを共通correlation IDにする。

# 14. Retry

AWS SDK:
- GET/Describe系はSDK標準retryを利用可
- Bedrock invoke retryは重複課金/Latencyを考慮し、明示設定をレビュー
- Application-level AI POST自動retryは無効

Client Transport Retry:
- timeout / response lost時は同一`practiceId`
- COMPLETEDなら保存済み結果
- PROCESSINGなら409
- FAILEDなら409

新しいBedrock実行を許可するのは、新しい練習intentとして新`practiceId`を採番した場合だけ。

---

## 参照公式ドキュメント

- [AWS Lambda - Reserved and provisioned concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [DynamoDB - Maximum throughput for on-demand tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html)
- [DynamoDB - TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

