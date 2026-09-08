---
document_id: DD-BE-001
title: "Backend詳細設計 BE01 API詳細設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 共通

Base:
`/v1`

Headers:
```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

全保護routeはAPI Gateway JWT Authorizerに加え、Lambda共通Auth Guardで以下を確認する。
- `token_use == "access"`
- `client_id == EXPECTED_APP_CLIENT_ID`
- `sub`
- 必要な`cognito:groups`
- `PROFILE.status == ACTIVE`

Responseには可能な限り:
```http
x-request-id: <request id>
```

を付与する。

# 2. Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "入力内容を確認してください。",
    "requestId": "..."
  }
}
```

内部exception、stack trace、PIIを返さない。

# 3. GET /v1/me

権限: USER / ADMIN

Response 200:
```json
{
  "userId": "cognito-sub",
  "name": "山田 太郎",
  "email": "masked-or-actual-as-policy",
  "status": "ACTIVE",
  "practiceCount": 34,
  "favoriteCount": 5,
  "lastPracticedAt": "2026-09-08T03:30:00.000Z"
}
```

# 4. POST /v1/practices

権限: USER / ADMIN

Request:
```json
{
  "practiceId": "uuid",
  "questionId": "job_change_001",
  "questionBankVersion": "questions-v1",
  "answer": "現在の仕事では..."
}
```

Validation:
- practiceId UUID
- questionId 1〜100 chars程度
- version allowlist
- answer 1〜2000 chars

First success: `201 Created`

Response:
```json
{
  "practiceId": "uuid",
  "questionId": "job_change_001",
  "category": "job_change",
  "question": "なぜ転職しようと思ったのですか？",
  "rating": "A",
  "goodPoint": "転職軸が明確",
  "improvement": "具体性を補う",
  "improvedAnswer": "...",
  "favorite": false,
  "createdAt": "2026-09-08T03:30:00.000Z"
}
```

初回開始時はDynamoDB Transactionで以下を同時に成立させる。
- `REQUEST#{practiceId}`を`PROCESSING`でConditional Put
- 当日`USAGE.aiInvocationCount`を上限条件付きで+1

Duplicate `COMPLETED` request:
- `200 OK`
- 保存済み結果を返す
- Bedrock再実行なし

`PROCESSING`:
- `409 PRACTICE_PROCESSING`
- Bedrock再実行なし
- Clientは同一`practiceId`で結果確認/通信再試行できる

`FAILED`:
- `409 PRACTICE_FAILED`
- 同一IDでBedrock再実行しない
- UIで新しい練習を開始する場合のみ新`practiceId`

Retry semantics:
- Transport Retry / response lost: same `practiceId`
- New Attempt after confirmed failure: new `practiceId`

# 5. GET /v1/practices

Query:
- `limit`: default 20, max 50
- `cursor`: opaque

Response:
```json
{
  "items": [],
  "nextCursor": "..."
}
```

Sort:
- createdAt descending

# 6. PATCH /v1/practices/{practiceId}/favorite

Request:
```json
{
  "favorite": true
}
```

Response:
```json
{
  "practiceId": "uuid",
  "favorite": true
}
```

同じ値を再送してもfavoriteCountを二重増減しない。

# 7. GET /v1/favorites

Query:
- limit
- cursor

ResponseはPracticeSummary配列。

# 8. GET /v1/admin/users

権限: ADMIN

Query:
- limit
- cursor
- status optional

Response:
```json
{
  "items": [
    {
      "userId": "...",
      "name": "...",
      "email": "...",
      "practiceCount": 10,
      "lastPracticedAt": "...",
      "status": "ACTIVE"
    }
  ],
  "nextCursor": "..."
}
```

# 9. POST /v1/admin/users

Request:
```json
{
  "name": "山田 太郎",
  "email": "user@example.com"
}
```

処理:
- Cognito AdminCreateUser
- USER group
- PROFILE
- 冪等収束

Response `201` or existing normalized `200`は詳細実装で統一する。
メール重複時は`409`を基本とする。

# 10. GET /v1/admin/users/{userId}

Response:
- profile
- practiceCount
- favoriteCount
- weekPracticeCount

# 11. GET /v1/admin/users/{userId}/practices

USER履歴と同じpagination。

# 12. PATCH /v1/admin/users/{userId}/status

Request:
```json
{
  "status": "DISABLED"
}
```

DisableはアプリAPIを先に閉じるため、状態収束型で以下を実施する。
1. DynamoDB `PROFILE.status=DISABLED`
2. Cognito `AdminDisableUser`
3. Cognito `AdminUserGlobalSignOut`

Enable:
1. Cognito `AdminEnableUser`
2. DynamoDB `PROFILE.status=ACTIVE`

サービス間Transactionはないため、途中失敗は管理APIを再実行して収束させる。

# 13. HTTP Status

| HTTP | Code |
|---|---|
| 400 | VALIDATION_ERROR |
| 401 | UNAUTHORIZED |
| 403 | FORBIDDEN / ACCOUNT_DISABLED |
| 404 | NOT_FOUND |
| 409 | CONFLICT / PRACTICE_PROCESSING / PRACTICE_FAILED |
| 429 | DAILY_LIMIT_EXCEEDED / RATE_LIMITED |
| 502 | AI_RESPONSE_INVALID |
| 503 | AI_UNAVAILABLE |
| 500 | INTERNAL_ERROR |

---

## 参照公式ドキュメント

- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

