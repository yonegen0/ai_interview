---
document_id: BD-ALL-001
title: "AI面接練習Webアプリ MVP 基本設計書（全体）"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. システム概要

転職支援者が登録した求職者のみ利用できる、一問一答型のAI面接練習Webアプリを提供する。

```text
USER / ADMIN
      │
      ▼
Next.js Static PWA
      │
      ├──────────────► Amazon Cognito
      │                 Email OTP
      │
      ▼
API Gateway HTTP API
JWT Authorizer
      │
      ▼
AWS Lambda (Python)
   ├── DynamoDB
   ├── Amazon Bedrock / Nova 2 Lite
   └── Cognito Admin API
```

静的WebコンテンツはCloudFront + Private S3から配信する。

# 2. 設計原則

1. 電車内・スマホで使いやすい
2. 1問約3分
3. AI待ち時間を短くする
4. 反復したくなる
5. 架空の経験・実績をAIが追加しない
6. 管理者が利用状況を把握できる
7. 低固定費
8. 保守しやすい
9. 技術選定よりプロダクト目的を優先

# 3. ユーザーと権限

| Role | 利用者 | 主機能 |
|---|---|---|
| USER | 求職者 | 練習、履歴、お気に入り |
| ADMIN | 転職支援者・運営 | USER機能 + ユーザー管理・履歴閲覧 |

認証はAmazon Cognito User Pool、認可の正データはCognito Groupとする。
DynamoDBにroleを持たせる場合も、認可判断には使用しない。

# 4. 認証

- Self-service sign-up: 無効
- 管理者作成のみ
- Email OTP Passwordless
- `EMAIL_OTP`
- `ALLOW_USER_AUTH`
- App ClientはPublic ClientとしてClient Secretを持たない
- `PreventUserExistenceErrors=ENABLED`
- APIにはAccess Tokenを送信
- API GatewayでJWT署名、issuer、audience/client_id、exp等を検証
- Lambda共通Auth Guardで`token_use == "access"`、`client_id == EXPECTED_APP_CLIENT_ID`、`sub`を必須確認
- Lambdaで`cognito:groups`を確認
- 全保護APIでDynamoDB `PROFILE.status == ACTIVE`を確認
- ADMIN APIは`ADMIN ∈ cognito:groups`を必須とする
- Cognito API認証で発行されるAccess TokenのscopeはMVP認可境界に使用しない

# 5. 機能一覧

## USER
- Login
- Category選択
- Question表示
- 回答入力
- AI評価
- 次の質問
- 履歴
- お気に入り
- Logout
- Offlineで過去履歴・お気に入り閲覧

## ADMIN
- User一覧
- User作成
- User有効/停止
- User詳細
- 練習履歴閲覧
- 累計/今週/お気に入り数確認

# 6. Question Bank

- 初期約100問
- AIで都度生成しない
- `questionId`は不変
- `questionBankVersion`を保持
- Git上の`resources/question-bank/`をCanonical Sourceとする
- Frontend/BackendへJSONを手作業コピーしない
- Build時にFrontendへcurrent version、Backendへcurrent + previous versionを生成/同梱する
- Build/CIで`questionBankVersion`と生成物hashの整合を検証する
- Backendは送信されたquestion本文を信用せず、`questionId + version`で正規データを解決
- 未回答優先
- 直近出題を避ける
- 全問回答後は再シャッフルまたは古い回答から再挑戦

# 7. AIフィードバック

入力:
- questionId
- questionBankVersion
- answer
- practiceId

出力:
- rating: S/A/B/C
- goodPoint
- improvement
- improvedAnswer

自由Markdownではなく、Nova Tool Useのnamed tool choiceを用いて構造化する。
Lambda側で以下を検証する。

1. `stopReason == "tool_use"`
2. 期待する`toolUse` blockが1件のみ存在
3. tool nameが`return_interview_feedback`
4. inputがJSON object
5. JSON Schema validation
6. business validation

# 8. AI事実制約

AIは入力にない以下を作らない。

- 職歴
- 役職
- 数値
- 売上実績
- 人数
- 資格
- スキル
- エピソード

回答内の「命令文」は面接回答本文として扱い、システム指示を上書きさせない。

# 9. データ

DynamoDB 1テーブルを基本とする。

主Item:
- PROFILE
- PRACTICE
- REQUEST / Idempotency
- USAGE

GSI:
- Admin User List
- Favorites

# 10. 冪等性

1回の論理送信につきFrontendで`practiceId`を生成する。

Bedrock実行前にDynamoDB `TransactWriteItems`で以下を原子的に成立させる。

```text
Put REQUEST#practiceId
  status = PROCESSING
  Condition = requestが存在しない

Update USAGE#YYYY-MM-DD
  aiInvocationCount += 1
  Condition = DAILY_FEEDBACK_LIMIT未満
```

どちらかのConditionに失敗した場合はTransaction全体を失敗させ、Bedrockを呼び出さない。

既存REQUEST:
- `COMPLETED`: 保存済み結果を返す
- `PROCESSING`: Bedrockを再実行せず`PRACTICE_PROCESSING`
- `FAILED`: Bedrockを再実行せず`PRACTICE_FAILED`

Retryルール:
- HTTP timeout / response lostなどのTransport Retry: **同一`practiceId`**
- Backendが`FAILED`を確定した後の新しい練習: **新しい`practiceId`**

これにより「レスポンスだけ失われた」ケースでのAI二重呼び出しを抑える。

# 11. オフライン

正データはDynamoDB。
ブラウザ側はIndexedDBに直近履歴・お気に入りをキャッシュする。

Offline:
- 過去履歴: 閲覧可
- お気に入り: 閲覧可
- AI評価: 不可
- 更新キュー: MVP対象外

IndexedDB:
- KeyにCognito `sub`を含める
- 未認証状態では履歴を表示しない
- ログアウト時にcurrent userのキャッシュを削除
- 起動/ログイン時にowner sub不一致データを削除
- 最終アクセスから30日で期限切れ
- 直近50件を保持目安とする
- 「この端末の履歴データを削除」操作を提供する
- JWT/OTP/Auth responseは保存しない

# 12. セキュリティ

- HTTPS
- S3 Private + OAC
- JWT Authorizer
- Lambdaで`token_use=access` / `client_id` / `sub`検証
- Cognito Group authorization
- `PROFILE.status=ACTIVE` gate
- ユーザー停止時は`PROFILE.status=DISABLED` + `AdminDisableUser` + `AdminUserGlobalSignOut`
- Token StorageはAmplify公式Token Provider + `sessionStorage`
- IAM最小権限
- CORS制限
- CloudFront Security Headers
- Static Export + MUIではrequest nonceを利用しない。CSPはStatic Hosting制約を前提に設計し、third-party scriptを原則追加しない
- `dangerouslySetInnerHTML`禁止
- PIIログ禁止
- Token/OTPログ禁止
- AI入力文字数上限
- Daily AI Limit
- Rate limiting
- Budget/Alarm

# 13. 非機能

| 項目 | 目標 |
|---|---|
| AI Feedback | 約3秒をUX目標、保証値ではない |
| 通常API | 原則1秒未満を目標 |
| 画面 | Mobile First |
| 可用性 | AWS Managed Serverless標準 |
| コスト | 数百〜数千円/月を目標 |
| データ整合 | DynamoDBの条件式/Transactionを利用 |
| ログ | PIIを原則含めない |

# 14. 環境

- dev
- prod

本番と開発でCognito User Pool、DynamoDB Table、Lambda、API、S3等を分離する。

# 15. MVPで採用しないもの

- EC2/ECS
- RDS
- FastAPI
- Redis
- SQS
- Step Functions
- Bedrock Agents
- AppSync
- Amplify Hosting
- Next.js Runtime Server
- Server Actions
- 完全Offline Sync

# 16. 未確定事項

- AI日次上限
- DynamoDB本体データ保持期間
- 本番ドメイン
- Budget閾値
- Lambda Reserved Concurrency

v1.1で確定:
- Token Storage: `sessionStorage`
- IndexedDB cache retention: 30日
- Transport Retry: same `practiceId`
- Question Bank配布: Canonical Sourceからbuild生成

---

## 参照公式ドキュメント

- [Amazon Cognito - Authentication flows / Passwordless](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html)
- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [Amazon Bedrock - Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [Amazon Nova 2 - Using tools](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-tools.html)
- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)
- [DynamoDB - On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [CloudFront - Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [Amazon Cognito - Understanding the access token](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Amazon Cognito - Token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)
- [DynamoDB - TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

