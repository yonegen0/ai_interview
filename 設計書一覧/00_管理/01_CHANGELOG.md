# CHANGELOG

> 文書バージョン: 2.3\
> 更新日: 2026-09-12
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## v2.3 - 2026-09-12

- 回答の上限をFrontend・Backend共通でUTF-16単位500文字へ変更。100〜300文字の推奨と本文非加工を維持。
- カウンター・エラー・Story・契約fixtureを更新。旧長文pending／Mock結果は移行対象外、通常下書きは保持。
- scoreの有限整数値表現を受理して整数出力。405にAllowヘッダーを追加。
- 文字数境界、送信抑止、下書き復元、score、HTTPヘッダーの検証を追加。
- 過去の2000文字仕様と失敗結果は[検証記録](../../docs/BACKEND_P1_VERIFICATION.md)に履歴として保持。

## v2.2 - 2026-09-11

- [ADR-003](../../docs/ADR-003-local-backend-foundation.md)によりP0・P1を実装。
- 添付実装計画を6 API・21問・メモリRepository・Fake Workerの詳細計画へ置換。
- Python 3.13・uv・Pydantic、本人スコープ、全POST冪等応答、ロック付き原子的更新を追加。
- GETとは独立した評価Worker、失敗確定、CLIデモ、pytest・Zod共通fixture・Backend CIを追加。
- ローカル業務検証と永続化・AWS実装前の必須判断を分け、P2〜P7の完了証拠を整理。
- 本番認証・永続化・外部AI・AWS操作・公開は実施しない。
- 詳細は[検証記録](../../docs/BACKEND_P1_VERIFICATION.md)を参照。

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
