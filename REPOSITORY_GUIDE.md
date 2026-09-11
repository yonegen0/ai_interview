# リポジトリ案内

このリポジトリは、転職者向け「隙間時間特化型・一問一答AI面接練習Webアプリ」のMVP設計資料とFrontend単体MVPをまとめたものです。

`frontend/` にMSWで練習開始から結果・再挑戦まで動作する実装があります。v2採用に関する差分は[ADR](docs/ADR-001-frontend-standalone-v2.md)、実装の通信仕様は[API契約](docs/FRONTEND_API_CONTRACT.md)が入口です。最初に全体像をつかむ場合は、[README](README.md) → [プロジェクト計画](01_project_plan/01_project_plan.md) → [全体基本設計](02_basic_design/01_overall_basic_design.md) の順で読むと把握しやすくなります。

## ディレクトリ構成

```text
ai_interview_mvp_design/
├── README.md                    # プロジェクト概要、主要方針、未確定事項
├── REPOSITORY_GUIDE.md          # この案内
├── docs/                       # v2 API契約・設計差分ADR
├── .github/workflows/           # Frontend CI
├── 01_project_plan/             # 目的、スコープ、体制、工程、品質方針
├── 02_basic_design/             # システム全体と各領域の基本設計
├── 03_detailed_design/          # Frontend／Backend／Infrastructureの詳細設計
└── frontend/
    ├── package.json             # Frontendの依存関係とnpm scripts
    ├── src/
    │   ├── app/                 # Static Exportのルート
    │   ├── components/          # 共通Atomic Designコンポーネント
    │   ├── features/            # home / interview / feedbackとFeature内Atomic階層
    │   ├── lib/                 # API・Schema・復旧保存
    │   ├── mocks/               # MSW・質問・Repository
    │   ├── providers/           # Query・Theme・Mock起動
    │   └── theme/theme.ts       # MUI共通テーマ
    ├── stories/                 # Components／PagesのAtomic Design Story
    ├── AGENTS.md                # Frontend作業ルール
    └── skills/                  # AI作業用のレビュー・記述スタイル手順
```

## 目的別の入口

| 知りたいこと | 最初に読むファイル | 補足 |
|---|---|---|
| プロダクトの概要 | [README](README.md) | 採用技術、設計方針、未確定事項を短く確認できます |
| MVPの目的・範囲・進め方 | [プロジェクト計画](01_project_plan/01_project_plan.md) | 成功条件、対象／対象外、マイルストーン、品質方針があります |
| システム全体像 | [全体基本設計](02_basic_design/01_overall_basic_design.md) | ユーザー、権限、認証、主要機能、データ、非機能を横断して説明しています |
| 画面・Frontend | [Frontend基本設計](02_basic_design/02_frontend_basic_design.md) | Next.js、画面、状態、PWA、UI、テストの基本方針です |
| API・データ・AI処理 | [Backend基本設計](02_basic_design/03_backend_basic_design.md) | API、認可、DynamoDB、Bedrock、Question Bankの基本方針です |
| AWS構成・運用 | [Infrastructure基本設計](02_basic_design/04_infrastructure_basic_design.md) | 配信、認証、API、DB、監視、コスト、復旧の基本方針です |
| 実装時の具体的な仕様 | [詳細設計](03_detailed_design/) | Frontend／Backend／Infrastructureに分かれています |
| 現在のFrontend実装 | [frontend/src](frontend/src/) | 練習・結果・API・MSW・共通UIがあります |
| Frontendの起動・依存関係 | [frontend/package.json](frontend/package.json) | npm scriptsと利用ライブラリを確認できます |

## Frontend実装マップ

### アプリ本体

- [layout.tsx](frontend/src/app/layout.tsx): メタデータ、Viewport、MUI ThemeProvider、CssBaselineを設定するルートレイアウト。
- [page.tsx](frontend/src/app/page.tsx): Home Feature Pageを描画するRoute Entryです。
- [theme.ts](frontend/src/theme/theme.ts): 色、Typography、角丸、ShadowなどのMUI共通テーマ。

### 機能と通信

- [home](frontend/src/features/home/): ヒーローと3ステップでアプリの目的と使い方を伝えるトップ画面。
- [interview](frontend/src/features/interview/): Molecules／Organisms／Templates／Pagesに分けた開始・質問・入力・送信・評価・復旧。
- [feedback](frontend/src/features/feedback/): Organisms／Pagesに分けた結果・再挑戦・次の質問。
- [API](frontend/src/lib/api/): Zod Schema、fetch、Timeout、エラー変換。
- [復旧保存](frontend/src/lib/storage/recovery.ts): 下書きと未確定要求のsessionStorage。
- [MSW](frontend/src/mocks/): 21問、Handler、タブ内／メモリRepository。
- [Provider](frontend/src/providers/AppProviders.tsx): Theme・Query・Mock起動待ち。
- [テスト](frontend/tests/): Logic・Integration・静的成果物のE2E。
- [Storybook](frontend/stories/): 175 Story。ComponentsはAtoms／Molecules／Organisms／Templates、画面ContainerはPagesに分類。
- [Story Fixture](frontend/stories/fixtures/index.ts): UUID・日時・Session・Evaluation・Feedback・100〜2001文字の決定的Fixture。
- [Story環境](frontend/stories/test-utils/storyEnvironment.tsx): StoryごとのQuery Client、Mock Repository、`pocket:*` Storage、Router初期化。
- [CI](.github/workflows/frontend.yml): lint・型・テスト・ビルド。

### 共通コンポーネント

- [Button.tsx](frontend/src/components/atoms/Button.tsx): MUI Buttonをラップした共通ボタン。
- [Link.tsx](frontend/src/components/atoms/Link.tsx): 下線付きリンクとブランド用テキスト型を備えた共通画面遷移リンク。
- [Input.tsx](frontend/src/components/atoms/Input.tsx): MUI TextFieldをラップした共通入力欄。
- [Select.tsx](frontend/src/components/atoms/Select.tsx): ラベル、選択肢、エラー表示を内包する共通Select。
- [Header.tsx](frontend/src/components/molecules/Header.tsx): Eyebrow、Title、Descriptionで構成される共通ヘッダー。
- [Dialog.tsx](frontend/src/components/organisms/Dialog.tsx): Title、Content、Actionsを受け取る共通ダイアログ。
- [AppShell.tsx](frontend/src/components/templates/AppShell.tsx): ブランドHeaderとPageContainerを構成する共通Template。

Atomic Designの依存方向は`Page → Template → Organism → Molecule → Atom`です。Feature固有ComponentはFeature境界を維持し、下位層から上位層を参照しません。

### 開発・確認

`frontend/` を作業ディレクトリにして実行します。

```bash
npm ci
npm run dev:mock   # http://localhost:3000
npm run lint
npm run typecheck
npm test
npm run build
npm run build:mock
npm run test:e2e
npm run storybook  # http://localhost:6006
npm run build-storybook
```

FrontendはNext.js 16、React 19、MUI 9、TypeScriptを利用しています。依存バージョンの正確な情報は[package.json](frontend/package.json)を参照してください。

## 設計書マップ

### 01_project_plan

- [01_project_plan.md](01_project_plan/01_project_plan.md): プロダクトの目的、背景、成功条件、MVPスコープ、体制、開発フェーズ、マイルストーン、品質方針。

### 02_basic_design

- [01_overall_basic_design.md](02_basic_design/01_overall_basic_design.md): システム全体の共通方針。設計判断の土台です。
- [02_frontend_basic_design.md](02_basic_design/02_frontend_basic_design.md): Next.js Frontend、画面、認証クライアント、PWA、UI、テスト。
- [03_backend_basic_design.md](02_basic_design/03_backend_basic_design.md): API、認証・認可、DynamoDB、AI処理、Question Bank、ログ。
- [04_infrastructure_basic_design.md](02_basic_design/04_infrastructure_basic_design.md): AWS構成、IaC、配信、監視、コスト、セキュリティ、バックアップ。

### 03_detailed_design/frontend

- [FE01_architecture_component_design.md](03_detailed_design/frontend/FE01_architecture_component_design.md): ディレクトリ、依存方向、コンポーネント区分、状態管理、実装規約。
- [FE02_screen_ui_ux_design.md](03_detailed_design/frontend/FE02_screen_ui_ux_design.md): ログイン、練習、履歴、お気に入り、管理画面の画面・状態・UX。
- [FE03_auth_api_tanstack_query_design.md](03_detailed_design/frontend/FE03_auth_api_tanstack_query_design.md): Cognito認証、Token、API Client、TanStack Query、エラー処理。
- [FE04_pwa_offline_cache_design.md](03_detailed_design/frontend/FE04_pwa_offline_cache_design.md): Service Worker、Cache Storage、IndexedDB、オフライン動作、更新UX。
- [FE05_storybook_test_accessibility_design.md](03_detailed_design/frontend/FE05_storybook_test_accessibility_design.md): Storybook、Vitest、Playwright、アクセシビリティ、CI品質ゲート。

### 03_detailed_design/backend

- [BE01_api_detailed_design.md](03_detailed_design/backend/BE01_api_detailed_design.md): REST APIのリクエスト、レスポンス、エラー、HTTP Status。
- [BE02_dynamodb_data_model_design.md](03_detailed_design/backend/BE02_dynamodb_data_model_design.md): DynamoDBの項目、Index、Transaction、整合性、TTL、PII。
- [BE03_cognito_auth_authorization_user_management.md](03_detailed_design/backend/BE03_cognito_auth_authorization_user_management.md): Cognito、Email OTP、Group、認可、ユーザー作成・停止。
- [BE04_bedrock_ai_feedback_design.md](03_detailed_design/backend/BE04_bedrock_ai_feedback_design.md): Bedrockモデル、Tool Use、評価Rubric、出力検証、AI品質。
- [BE05_idempotency_usage_limit_error_log_design.md](03_detailed_design/backend/BE05_idempotency_usage_limit_error_log_design.md): 冪等性、利用上限、再試行、ログ、メトリクス、エラー対応。
- [BE06_question_bank_logic_design.md](03_detailed_design/backend/BE06_question_bank_logic_design.md): Question Bankの形式、ID、配布、選択、回答済み判定、互換性。

### 03_detailed_design/infrastructure

- [INF01_cdk_stack_environment_design.md](03_detailed_design/infrastructure/INF01_cdk_stack_environment_design.md): CDK Stack、環境、設定値、出力、依存関係、デプロイ順。
- [INF02_s3_cloudfront_web_delivery_design.md](03_detailed_design/infrastructure/INF02_s3_cloudfront_web_delivery_design.md): S3、CloudFront、OAC、Cache、CSP、TLS、Webデプロイ。
- [INF03_api_gateway_lambda_iam_design.md](03_detailed_design/infrastructure/INF03_api_gateway_lambda_iam_design.md): HTTP API、Route、Authorizer、Lambda、IAM、制限、Access Log。
- [INF04_cognito_ses_design.md](03_detailed_design/infrastructure/INF04_cognito_ses_design.md): Cognito User Pool、App Client、Group、SES、メール、監視。
- [INF05_dynamodb_bedrock_design.md](03_detailed_design/infrastructure/INF05_dynamodb_bedrock_design.md): DynamoDBの保護・容量とBedrockのRegion・IAM・ログ・コスト。
- [INF06_monitoring_cost_security_operations.md](03_detailed_design/infrastructure/INF06_monitoring_cost_security_operations.md): Metrics、Alarm、Log、コスト防御、セキュリティ、障害対応、Backup、Release。

## よくある作業ごとの参照先

| 作業 | 主な参照先 |
|---|---|
| 画面を実装する | FE01 → FE02 → FE03。PWA対象ならFE04、Story/TestならFE05も参照 |
| APIを実装する | BE01 → BE02 → BE03。AI評価ならBE04、冪等性・制限ならBE05も参照 |
| 質問選択を実装する | BE06を中心に、Frontend側の選択責務はFE01／FE02も参照 |
| AWS CDKを実装する | INF01から開始し、対象サービスに応じてINF02〜INF06を参照 |
| 認証・認可を変更する | FE03、BE03、INF03、INF04を横断して確認 |
| AIフィードバックを変更する | BE04、BE05、INF05、INF06を横断して確認 |
| オフライン仕様を変更する | FE04を中心に、全体基本設計のオフライン方針も確認 |
| セキュリティ／コストを確認する | 全体基本設計、BE05、INF03〜INF06を確認 |

## 文書間で矛盾した場合

[README](README.md) に定義された優先順位に従います。

1. 最新の承認済みADR・変更記録
2. 詳細設計書
3. 基本設計書
4. プロジェクト計画書
5. 過去の会話・検討メモ

外部サービスやライブラリの仕様は、最新の公式ドキュメントを優先します。

## 現状の注意点

- FrontendはMSWによる単体MVPです。実AI・認証・実Backend・履歴・PWAは未実装です。
- 旧BE01の同期APIとv2は互換ではありません。[API契約](docs/FRONTEND_API_CONTRACT.md)と[ADR](docs/ADR-001-frontend-standalone-v2.md)を優先してください。
- 本番成果物は `out/`、Mock検証用は `out-mock/`。Mock成果物は公開用ではありません。
- Storybookは公式Next.js Navigation Mockを利用し、旧独自Aliasと重複Preview Setupは使用しません。
- `frontend/skills/` は補助資料で、一部に他プロダクトの例が残っています。現在の作業規則は[AGENTS.md](frontend/AGENTS.md)です。
- データはタブ内保存で、タブを閉じた後の復元は保証しません。

## 更新時のチェック

- 基本設計を変更した場合、対応するFrontend／Backend／Infrastructureの詳細設計も確認する。
- API、認証、データモデルは複数領域にまたがるため、片方だけを更新しない。
- ファイルを追加・削除した場合は、READMEの構成図とこの案内を合わせて更新する。
- 未確定値を決めた場合は、READMEの「設計上の未確定事項」と該当設計書を更新する。
