---
document_id: BD-BE-001
title: "AI面接練習Webアプリ MVP 基本設計書（バックエンド）"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 構成

```text
API Gateway HTTP API
  ↓
Lambda
├─ feedback
├─ history
├─ profile
└─ admin
  ↓
DynamoDB / Bedrock / Cognito
```

Python Lambda Handlerを直接使用し、MVPではFastAPIを導入しない。

# 2. API

Base path: `/v1`

- `GET /me`
- `POST /practices`
- `GET /practices`
- `PATCH /practices/{practiceId}/favorite`
- `GET /favorites`
- `GET /admin/users`
- `POST /admin/users`
- `GET /admin/users/{userId}`
- `GET /admin/users/{userId}/practices`
- `PATCH /admin/users/{userId}/status`

# 3. 認証・認可

API Gateway:
- JWT署名
- issuer
- audience/client_id
- exp等

Lambda共通Auth Guard:
- `token_use == "access"`
- `client_id == EXPECTED_APP_CLIENT_ID`
- `sub`存在
- `cognito:groups`
- DynamoDB `PROFILE.status == ACTIVE`
- ADMIN endpointでは`ADMIN` group必須

API Gateway JWT Authorizer単独ではAccess TokenとID Tokenを標準的に区別できないため、`token_use`をLambdaで必須検証する。
Cognito API認証のAccess Tokenは通常`aws.cognito.signin.user.admin` scopeのみとなるため、MVPではcustom route scopeを認可境界にしない。

USER APIでクライアント送信userIdを本人判定に使わない。

# 4. DynamoDB

1テーブル:
- PROFILE
- PRACTICE
- REQUEST
- USAGE

On-Demandを利用する。

REQUEST itemは:
- practiceId lookup
- idempotency lock
- practice SK解決

を兼ねる。

# 5. AI処理

1. request validation
2. Auth Guard（Access Token / Group / PROFILE ACTIVE）
3. questionId/version解決
4. DynamoDB Transactionで`REQUEST=PROCESSING`作成 + `USAGE.aiInvocationCount`加算
5. Prompt構築
6. Bedrock Converse
7. `stopReason == "tool_use"`確認
8. 期待named Tool Callが1件のみであることを確認
9. Schema / business validation
10. DynamoDB TransactionでPractice保存・REQUEST COMPLETED・集計更新
11. Response

Nova Tool Useは外部操作ではなく構造化レスポンス専用に使用する。

# 6. 失敗時方針

- AI POSTのクライアント自動retryはしない
- Transport Retryでは同一`practiceId`を使用する
- `COMPLETED`は保存済み結果を返しBedrock再実行なし
- `PROCESSING`はBedrock再実行なし
- `FAILED`は同一IDでBedrock再実行せず、新しい練習時に新`practiceId`
- PIIをログへ出さない
- 例外本文をクライアントへ返さない

# 7. ユーザー作成

AdminCreateUser → Group追加 → PROFILE作成。

サービス間Transactionはないため、処理を冪等化し、
途中失敗時に再実行して収束できるようにする。

# 8. Question Bank

Git上の`resources/question-bank/`をCanonical Sourceとする。
Backend packageにはbuild生成したcurrent + previous versionを同梱する。
Frontend/BackendへのJSON手動コピーは禁止する。
CIでversion/hash整合を検証する。

# 9. 利用量

- `USAGE#{JST date}`
- `aiInvocationCount`
- `completedPracticeCount`とは分離
- 条件式で日次上限を制御

# 10. ログ

記録:
- requestId
- route
- status
- latency
- model
- promptVersion
- errorType
- token usage（取得可能範囲）

禁止:
- answer
- improvedAnswer
- email
- name
- JWT
- OTP

---

## 参照公式ドキュメント

- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [DynamoDB - On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [Amazon Bedrock - Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [Amazon Nova 2 - Using tools](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-tools.html)
- [Amazon Cognito - AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)
- [Amazon Cognito - Understanding the access token](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [DynamoDB - TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

