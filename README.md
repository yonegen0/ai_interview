# AI面接練習Webアプリ MVP

更新日: 2026-09-08  
版: 1.1

## 文字コード・ZIP互換性

- Markdown本文はUTF-8です。
- ZIP内のファイル名はWindows標準展開でも文字化けしにくいASCII英数字へ統一しています。
- 文書本文・見出しは日本語のままです。

## このフォルダについて

転職者向け「隙間時間特化型・一問一答AI面接練習Webアプリ」のMVPプロジェクトです。

プロジェクト計画・基本設計・詳細設計に加え、`frontend/` にNext.jsによるFrontendの初期実装があります。目的の資料やコードを探す場合は、[リポジトリ案内](REPOSITORY_GUIDE.md)を参照してください。

設計方針は以下です。

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

- `frontend/src/app/layout.tsx`: MUIテーマ、メタデータ、Viewportを設定したルートレイアウト
- `frontend/src/app/page.tsx`: 練習カテゴリを選択する仮トップ画面
- `frontend/src/components/`: Button、Input、Select、Header、Dialogの共通UI
- `frontend/src/lib/theme.ts`: セージグリーンを基調としたMUI共通テーマ
- `frontend/stories/`: 共通UIのStorybook Story（一部に未実装ファイルへの参照あり）
- BackendおよびInfrastructureは設計段階で、実装コードはまだありません

トップ画面は仮実装です。認証、API接続、質問表示、回答送信、AIフィードバック、履歴、お気に入りは未接続です。

## Frontendの起動

Node.jsとnpmを用意し、`frontend/` で実行します。

```bash
cd frontend
npm install
npm run dev
```

ブラウザで <http://localhost:3000> を開きます。

```bash
npm run lint       # ESLint
npm run build      # Production build
npm run storybook  # Storybook（port 6006）
```

現状の `npm run build` は、既存のStorybookファイルが未実装の `AppShell` やモックを参照しているため、プロジェクト全体の型検査で停止します。

## リポジトリ構成

```text
ai_interview_mvp_design/
├── README.md
├── REPOSITORY_GUIDE.md
├── 01_project_plan/
│   └── 01_project_plan.md
├── 02_basic_design/
│   ├── 01_overall_basic_design.md
│   ├── 02_frontend_basic_design.md
│   ├── 03_backend_basic_design.md
│   └── 04_infrastructure_basic_design.md
├── 03_detailed_design/
    ├── frontend/
    │   ├── FE01_architecture_component_design.md
    │   ├── FE02_screen_ui_ux_design.md
    │   ├── FE03_auth_api_tanstack_query_design.md
    │   ├── FE04_pwa_offline_cache_design.md
    │   └── FE05_storybook_test_accessibility_design.md
    ├── backend/
    │   ├── BE01_api_detailed_design.md
    │   ├── BE02_dynamodb_data_model_design.md
    │   ├── BE03_cognito_auth_authorization_user_management.md
    │   ├── BE04_bedrock_ai_feedback_design.md
    │   ├── BE05_idempotency_usage_limit_error_log_design.md
    │   └── BE06_question_bank_logic_design.md
    └── infrastructure/
        ├── INF01_cdk_stack_environment_design.md
        ├── INF02_s3_cloudfront_web_delivery_design.md
        ├── INF03_api_gateway_lambda_iam_design.md
        ├── INF04_cognito_ses_design.md
        ├── INF05_dynamodb_bedrock_design.md
│       └── INF06_monitoring_cost_security_operations.md
└── frontend/
    ├── package.json
    ├── src/
    │   ├── app/                 # App RouterのLayoutと仮トップ画面
    │   ├── components/          # 共通UIコンポーネント
    │   └── lib/theme.ts         # MUIテーマ
    ├── stories/                 # Storybook Story
    └── skills/                  # AI作業用の補助手順
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
