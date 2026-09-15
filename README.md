# AI面接練習Webアプリ MVP

更新日: 2026-09-12。設計書v2.3対応。Markdown本文はUTF-8です。

転職者がスマートフォンで一問ずつ面接練習するWebアプリです。
現Frontendは認証なしのMSW単体MVPとして、回答・評価待機・結果・再挑戦・次問・再読み込み復旧まで実装しています。

## 資料と正本

- [設計書一覧](設計書一覧/00_管理/00_設計書一覧.md)：現行の計画・基本・詳細・横断・テスト設計。
- [リポジトリ案内](REPOSITORY_GUIDE.md)：構成と実装への入口。
- [ADR-002](docs/ADR-002-frontend-contract-alignment.md)：現Frontend契約を採用する判断。
- [実装計画](AI面接練習Webアプリ｜実装計画.md)：P0・P1の仕様とP2〜P7の着手条件。
- [ADR-003](docs/ADR-003-local-backend-foundation.md)：メモリ＋FakeのローカルBackendを先行する判断。
- [P3実装・検証記録](docs/P3_VERIFICATION.md)：DynamoDB・処理権・配送回復の実装、Python試験、P4実DB検証手順。
- [Backend README](backend/README.md)：セットアップ、6 API、明示Worker、保証範囲。
- [API契約](docs/FRONTEND_API_CONTRACT.md)：HTTP・冪等性・復旧の正本。
- [Zod Schema](frontend/src/lib/api/schemas/index.ts)：Request／Responseの型・制約の正本。
- [次工程の必須事項](設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)：未確定事項と完了条件。

最新の承認済みADRを判断の根拠とし、契約・Schema・設計書を連動して更新します。
旧同期API等の履歴は[ADR-001](docs/ADR-001-frontend-standalone-v2.md)に残しています。
外部サービスの仕様は実装時に最新の公式ドキュメントで確認します。

## 現在の実装と将来構成

実装済みは7カテゴリ・21問、Session／Attempt／Evaluationの6 Routeを使うMock練習、
100点評価とフィードバック、同一キーでの手動再確認、sessionStorage復旧、
Storybook・Vitest・Playwright・Frontend GitHub Actionsです。
P1としてPythonの6 API・メモリRepository・Fake Provider・明示Worker・Backend CIを追加しています。
P3のDynamoDB Repository、Dispatch outbox、処理権・開始記録、配送回復、内部入力adapterを実装しました。
現在は「P3実装完了・Python検証完了・実DB検証待ち」。2026-09-13のレビュー修正・番号別証拠は[検証記録](docs/P3_VERIFICATION.md)を参照。実AWS試験はP4へ引き継ぎます。
Frontendは引き続きMSWで動作し、このローカルBackendとは未接続です。

将来構成はCognito Email OTP（管理者登録、USER／ADMIN）、
API Gateway HTTP API＋JWT Authorizer、Python Lambdaの3責務、
DynamoDB On-Demand 1 Table、OpenAI Responses API、
Terraform、Private S3＋CloudFront OACです。
モデルと本番OpenAI認証は候補段階で、Backend工程で検証します。

認証・実AI・永続化Backend・履歴・お気に入り・PWA・AWS公開は未実装です。
回答受付の202と評価GETは契約として採用済みですが、非同期起動方式・受付と起動の整合・
重複／期限切れ回復・物理データ設計はP2（永続化・AWS着手前）で確定します。
接続準備は実API接続完了を意味しません。

## 起動・検証

[Backend P1検証記録](docs/BACKEND_P1_VERIFICATION.md)と[Backend手順](backend/README.md)を参照してください。
BackendはPython 3.13・uvで `uv sync --locked`、`uv run --locked pytest -q`、
`uv run --locked interview-demo` をbackend/から実行します。HTTPサーバー・公開用Lambdaではありません。

[v2.1検証記録](docs/FRONTEND_ALIGNMENT_VERIFICATION.md)に今回のテスト・ビルド結果と既知失敗を記載しています。
[P1検証記録](docs/BACKEND_P1_VERIFICATION.md)に回答上限500文字、score、405と最新の全体検証結果を記載しています。

Node.js 22以上。CIも22を使用します。

```bash
cd frontend
npm ci
npm run dev:mock
```

[Frontend README](frontend/README.md)にStorybook・検証方法と画像仕様を記載しています。
通常のdevはMockを強制有効化しません。[環境変数例](frontend/.env.example)を参照してください。

```bash
npm run lint
npm run typecheck
npm test -- --testTimeout=15000
npm run build
npm run build:mock
npm run build-storybook
npm run test:e2e
```

本番成果物はout/、Mock検証用はout-mock/。Mock成果物は公開用ではありません。
WebP実寸法とE2Eの512px期待値に既知の不一致があります。過去の成功件数は現在の成功保証ではありません。

## リポジトリ構成

- 設計書一覧/：現行設計書体系。
- docs/：採用ADR・API契約・検証記録。
- frontend/：Next.js単体MVPとテスト。
- backend/：ローカル6 API・メモリ・Fake・Worker・pytest。
- contracts/：Python HandlerとFrontend Zodの共通fixture。
- .github/workflows/：Frontend CI・Backend CI（デプロイなし）。

旧設計書の整理による作業ツリー上の削除状態はそのまま保持します。
