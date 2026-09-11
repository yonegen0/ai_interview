# AI面接練習Webアプリ MVP

更新日: 2026-09-08  
版: 1.1

## 文字コード・ZIP互換性

- Markdown本文はUTF-8です。
- ZIP内のファイル名はWindows標準展開でも文字化けしにくいASCII英数字へ統一しています。
- 文書本文・見出しは日本語のままです。

## このフォルダについて

転職者向け「隙間時間特化型・一問一答AI面接練習Webアプリ」のMVPプロジェクトです。

プロジェクト計画・基本設計・詳細設計に加え、`frontend/` にNext.jsによるFrontend単体MVPがあります。目的の資料やコードを探す場合は、[リポジトリ案内](REPOSITORY_GUIDE.md)を参照してください。

以下は将来の全体構想です。今回のFrontend単体MVPは認証なし・MSWによる固定サンプル評価で動作します。v2採用の変更点は[ADR-001](docs/ADR-001-frontend-standalone-v2.md)、接続契約は[Frontend API契約](docs/FRONTEND_API_CONTRACT.md)を参照してください。

- スマートフォン・電車内・1問約3分を最優先
- 一般公開せず、管理者が登録した求職者だけ利用
- Passwordless Email OTP
- Next.js App RouterをStatic Exportし、S3 + CloudFrontから配信
- API Gateway HTTP API + Lambda + DynamoDB
- Amazon Bedrock / Amazon Nova 2 Liteを第一候補
- Question Bank方式。質問の都度AI生成はしない
- Question BankはGit上の単一Canonical SourceからFrontend/Backend配布物をbuild生成する
- 回答本文等の個人情報をログへ不用意に出さない
- Bedrock二重呼び出し・利用量暴走を多層で防止
- Access TokenはLambdaで`token_use=access` / `client_id` / Group / `PROFILE.status`まで検証する
- 認証TokenはAmplify公式Token Provider + `sessionStorage`をMVP標準とする
- 外部仕様は最新の公式ドキュメントを最優先

## v1.1 主要修正

- API Gateway JWT Authorizerに加え、Lambda共通Auth Guardで`token_use=access`、`client_id`、`sub`、`cognito:groups`、`PROFILE.status=ACTIVE`を確認
- ユーザー停止は`PROFILE.status=DISABLED`を先に反映し、`AdminDisableUser` + `AdminUserGlobalSignOut`へ収束
- `REQUEST`作成と`USAGE.aiInvocationCount`加算を`TransactWriteItems`で原子的に開始
- 通信再送は同一`practiceId`、新しい練習だけ新`practiceId`
- Nova Tool Use応答は`stopReason=tool_use`、期待Toolが1件のみであることまで検証
- Static Export + MUIのCSP制約を明記し、MVPではnonce方式を採用しない
- `useSearchParams()`を利用するStatic Routeでは`Suspense`境界を必須化
- IndexedDBのユーザー分離、30日キャッシュ期限、起動時クリーンアップ、手動削除を追加
- AWS Budgets / API Gateway throttling / DynamoDB Maximum ThroughputをHard Cost Capとみなさないことを明記

## 現在の実装状況

- 7カテゴリ・21問の練習開始、回答入力、非同期評価待機、結果表示。
- 同じ質問への再挑戦、次の質問、通信失敗時の同一要求再確認。
- Zod API契約、TanStack Query、React Hook Form、MSW、sessionStorageによる下書き・処理復旧。
- 共通テーマ、170 StoryのStorybook（Components／PagesのAtomic Design階層）、単体・統合・静的成果物上のE2E、GitHub Actions。
- 認証、実AI評価、実Backend、履歴、PWA、AWS公開は今回の対象外です。

## Frontendの起動

Node.js 22以上を使用します。

```bash
cd frontend
npm ci
npm run dev:mock
```

ブラウザで <http://localhost:3000> を開きます。評価は固定サンプルです。

```bash
npm run lint
npm run typecheck
npm test
npm run build           # 本番用 out/。Mock Workerを除去
npm run build:mock      # 検証用 out-mock/
npm run test:e2e        # out-mock/をローカル配信して検証
npm run storybook       # port 6006
npm run build-storybook
```

通常の `npm run dev` はMockを強制有効化しません。環境設定は[frontend/.env.example](frontend/.env.example)を参照してください。
実Backend接続には新API契約への対応と認証実装が必要です。

## リポジトリ構成

```text
ai_interview_mvp_design/
├── README.md / REPOSITORY_GUIDE.md
├── docs/                        # v2 API契約、採用ADR
├── 01_project_plan/             # プロジェクト計画
├── 02_basic_design/             # 全体・各領域の基本設計
├── 03_detailed_design/          # frontend / backend / infrastructure
├── .github/workflows/           # Frontend CI
└── frontend/
    ├── src/
    │   ├── app/                # 静的ルート
    │   ├── features/           # interview / feedbackとFeature内Atomic Component
    │   ├── lib/                # API契約・Client・復旧保存
    │   ├── mocks/              # Handler・21問・Mock Repository
    │   ├── providers/          # Theme・Query・Mock起動
    │   ├── components/         # 共通Atoms／Molecules／Organisms／Templates
    │   └── theme/              # MUIテーマ
    ├── stories/                # Components／PagesのAtomic Design Story
    │   ├── fixtures/           # Zod検証済み固定Fixture
    │   └── test-utils/         # Query・MSW・Storage・Router隔離
    ├── tests/                  # 単体・統合・E2E
    ├── scripts/                # ビルド・静的配信
    └── skills/                 # AI作業補助資料
```

## 設計上の未確定事項

次の値は実装を止めないため設計上パラメータ化し、運用開始前までに確定します。

| 項目 | 状態 | 設計上の扱い |
| --- | --- | --- |
| 1ユーザー1日のAI上限 | TBD | `DAILY_FEEDBACK_LIMIT` |
| 本番独自ドメイン | TBD | CloudFront/APIの設定値として差し替え可能 |
| データ保存期間 | TBD | TTL/削除運用を後付け可能にする |
| AWS Budget閾値 | TBD | 環境別パラメータ |
| IndexedDB保持件数 | 初期値確定 | 直近50件を上限目安。PIIを含むキャッシュは最終アクセスから30日で期限切れ |
| Lambda Reserved Concurrency | TBD | 負荷・Bedrock制限を見て決定 |
| 認証トークンの永続化方式 | v1.1で確定 | Amplify Authの`sessionStorage`。Strict nonce CSPが必要になった場合はStatic Exportを含めBFF/Runtime構成をADRで再設計 |

## ドキュメント優先順位

矛盾がある場合は、以下の順に新しい判断を正とします。

1. 最新の承認済みADR・変更記録
2. 詳細設計書
3. 基本設計書
4. プロジェクト計画書
5. 過去の会話・検討メモ

外部サービス・ライブラリの仕様は、常に最新公式ドキュメントを優先します。
