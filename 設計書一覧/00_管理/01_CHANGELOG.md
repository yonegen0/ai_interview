# CHANGELOG

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## v2.1 - 2026-09-11

- [ADR-002](../../docs/ADR-002-frontend-contract-alignment.md)に従い現Frontend契約を採用。
- Session／Attempt／Evaluationの6 Route、202受付とGET、100点scoreと指摘配列へ統一。
- 全POSTのIdempotency-KeyとBackend生成リソースIDを分離。
- Frontend配置・復旧・ポーリング・静的URLを実装に整合。
- 論理モデルにSession・Attempt・冪等要求を追加。非同期実行・物理設計の必須決定事項を明記。
- CORSにIdempotency-Keyを追加し、Frontend CI実装済みと全体CI/CD未確定を区別。
- FORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERRORの日本語表示と関連検証を追加。
- 文書入口・リンクを更新。認証・Backend・AWS・画像再生成は今回の対象外。

## v2.0 - 2026-09-11（履歴。冪等性・評価契約はv2.1で更新）

### Architecture
- CloudFront FunctionsによるURL Rewriteを追加。
- Cognito Email OTP Passwordless認証を明文化。
- API Gateway HTTP APIのCORS設計を追加。
- `admin-api`で`cognito:groups=ADMIN`を再検証する方針を追加。
- Evaluation Idempotencyを`evaluationId`中心へ変更。
- OpenAI Production認証にAWS Workload Identity Federationを第一候補として追加。
- GPT-5.6 Luna固定ではなくLuna / Terra比較評価を追加。
- Terraform state bootstrapとS3 native lockingを明文化。

### Documents
- Backend詳細設計をAPI / DynamoDB / Lambda / OpenAI / Retry / Idempotency / Authorizationに再編。
- Infrastructure詳細設計をTerraform / Cognito / API Gateway / IAM / DynamoDB / Frontend Hosting / OpenAI Auth / Monitoring / CI/CDに再編。
- AIモデル評価設計書を追加。
