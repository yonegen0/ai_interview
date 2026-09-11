# ADR-002: 現Frontend契約を全体設計へ整合する

状態: ユーザー承認済み計画に基づく採用。日付: 2026-09-11。

## 背景と判断

設計書v2.0の同期評価案とFrontend単体MVPには、API、評価形式、冪等性、配置の差がある。
現FrontendのSession／Attempt／Evaluationは再読み込み復旧、応答消失後の再確認、再挑戦、次問遷移を支える。
これを採用契約として設計書v2.1へ反映し、画面・Hook・Reducer・保存version・URLは維持する。

| v2.0の旧案（不採用） | v2.1の採用 |
|---|---|
| POST /evaluationsで同期評価 | 回答POSTの202受付、評価GET、Feedback GET |
| Frontend生成evaluationIdで冪等制御 | 全POSTのIdempotency-Key。各リソースIDはBackend生成 |
| rating、goodPoint、improvement、improvedAnswer | score、summary、strengths、improvements、任意exampleAnswer |
| shared/api・shared/schema | 現在のsrc/lib/api・src/lib/api/schemas |

## 正本と優先関係

| 情報 | 正本 |
|---|---|
| Request／Responseの型・入力制約 | [Zod Schema](../frontend/src/lib/api/schemas/index.ts) |
| HTTP Status・冪等性・復旧動作 | [API契約](FRONTEND_API_CONTRACT.md) |
| 今回の採用判断・旧案との関係 | 本ADR |
| Backend・Infrastructure構成 | [設計書一覧](../設計書一覧/00_管理/00_設計書一覧.md)の基本・詳細設計 |
| 未確定事項と次工程 | [決定事項・未確定事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md) |

[ADR-001](ADR-001-frontend-standalone-v2.md)は履歴として保持する。最新の承認済みADRを判断の根拠とし、
契約・Schemaの矛盾を勝手な変換層で吸収せず、対応する正本を一緒に更新する。

## 継続する方針と今回の範囲

Cognito Email OTP、本人データの認可、ADMIN再認可、OpenAI、DynamoDB 1 Table、
Lambda 3責務、Terraform、Private S3＋CloudFrontの方針を継続する。
モデル・WIF・SDK等の候補は採用済み実装ではなく、Backend工程で公式仕様と互換性を検証する。

今回の実装はFORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERRORの日本語表示と関連テスト。
API形式、通信制御、UI、画像、依存バージョン、認証実装、AWS構築は変更しない。
接続準備完了は実API接続完了ではない。

## Backendに要求する動作

6エンドポイント、UUID、100点評価と配列の指摘、全POSTの冪等性をAPI契約に合わせる。
回答受付を永続化して202を返し、評価を継続して保存する。GETは保存済み状態を参照する。
Frontendの120秒自動確認停止は評価失敗・キャンセルを意味しない。
MSWの取得回数による完了処理はテスト専用であり、Backendの実行方式に流用しない。

## 実API接続までの工程

1. 非同期起動方式、受付保存と起動の整合、起動漏れ・重複・期限切れの回復を設計する。
2. DynamoDB物理キー・GSI・Transaction・保存期限、LambdaのRoute担当とIAMを確定する。
3. AI出力検証、モデル・認証方式、外部呼出の応答消失時の再実行方針を確定する。
4. BackendとAWSを実装し、本人認可、冪等性、処理滞留監視を検証する。
5. Cognitoログイン、Token更新、認証切れ、ログアウト時のCache・保存情報処理を実装する。
6. 実Backend版の練習・復旧E2Eを検証する。

非同期実行方式は本ADRでは選定しない。レスポンス返却後に同じLambda処理が継続する前提を置かない。
