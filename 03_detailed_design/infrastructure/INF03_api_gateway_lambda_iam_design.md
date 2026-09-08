---
document_id: DD-INF-003
title: "Infrastructure詳細設計 INF03 API Gateway・Lambda・IAM設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. HTTP API

Amazon API Gateway HTTP APIを採用。

理由:
- JWT Authorizer
- Lambda integration
- CORS
- 低コスト
- MVPにUsage Plan不要

# 2. Routes

- GET /v1/me
- POST /v1/practices
- GET /v1/practices
- PATCH /v1/practices/{practiceId}/favorite
- GET /v1/favorites
- GET /v1/admin/users
- POST /v1/admin/users
- GET /v1/admin/users/{userId}
- GET /v1/admin/users/{userId}/practices
- PATCH /v1/admin/users/{userId}/status

全route原則JWT必須。

# 3. Authorizer

Issuer:
Cognito User Pool issuer

Audience:
App Client ID

API Gateway JWT Authorizerは署名・issuer・audience/client_id・期限等を検証する。
Access Tokenに`aud`がない場合、API Gatewayは`client_id`をaudienceと照合する。

ただしAccess TokenとID Tokenを標準的に区別する仕組みはないため、Lambda共通Auth Guardで必ず以下を追加検証する。
- `token_use == "access"`
- `client_id == EXPECTED_APP_CLIENT_ID`
- `sub`
- `cognito:groups`
- `PROFILE.status == ACTIVE`

MVPではCognito API認証のAccess Tokenを使用するため、custom authorization scopeをrouteへ要求しない。

# 4. CORS

AllowOrigin:
- prod CloudFront domain/custom domain
- dev localhost only in dev

Methods:
GET, POST, PATCH, OPTIONS

Headers:
Authorization, Content-Type

`*`をprodで使用しない。

# 5. Lambda

Functions:
- feedback
- history
- profile
- admin

Runtime:
Pythonの実装時点でサポート中の安定版を公式確認して採用。

Architecture:
arm64第一候補。依存互換を確認。

# 6. Timeout

- feedback: AI latencyを考慮し余裕を持つ
- others: 短め

具体秒数は実測後確定。

# 7. Memory

feedbackはCPUも増えるため256〜512MB程度から計測。
他Functionは128〜256MB程度から計測。

固定せずLambda Power Tuning相当の実測を優先。

# 8. IAM

## feedback
- Table Get/Put/Update/Transact/Query（必要範囲）
- PROFILE status確認用Get
- Bedrock Converse/Invokeに必要な権限
- CloudWatch Logs

## history
- Table Get/Query/Update/Transact
- PROFILE status確認用Get
- Bedrockなし

## profile
- Table Get

## admin
- Table Get/Query/Put/Update/Transact
- Cognito AdminCreateUser
- AdminAddUserToGroup
- AdminEnableUser
- AdminDisableUser
- AdminUserGlobalSignOut
- 必要なread
- Bedrockなし

Resource ARNを可能な限り限定。

# 9. Concurrency

feedback:
Reserved Concurrencyを設定候補。
TBD。

Admin/historyは通常設定。

Provisioned ConcurrencyはMVP初期なし。

# 10. Throttling

HTTP API stage/route throttling。
AI routeを最も厳しくする。

API Gateway HTTP API throttlingはAWS公式上best-effort targetであり、保証されたHard Ceilingとして扱わない。
厳密なユーザー日次QuotaはDynamoDB `USAGE`のConditionで制御する。

# 11. WAF

HTTP APIへのAPI Gateway直接WAF関連付けは前提にしない。
WAF必須化時はアーキテクチャADR。

# 12. Access Logs

PIIを含まないformatにする。
Authorization header/bodyを記録しない。

---

## 参照公式ドキュメント

- [API Gateway - Choose between REST APIs and HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [API Gateway - AWS WAF for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html)
- [AWS Lambda - Reserved and provisioned concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

