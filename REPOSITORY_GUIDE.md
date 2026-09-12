# リポジトリ案内

更新日: 2026-09-12。設計書v2.3対応。

## 最初に読む資料

[README](README.md) → [設計書一覧](設計書一覧/00_管理/00_設計書一覧.md) →
[ADR-002](docs/ADR-002-frontend-contract-alignment.md) → [API契約](docs/FRONTEND_API_CONTRACT.md)。
型・制約は[Zod Schema](frontend/src/lib/api/schemas/index.ts)を正本とします。

## 目的別の入口

| 目的 | 資料 |
|---|---|
| 計画・現在地 | [プロジェクト計画](設計書一覧/01_プロジェクト/01_プロジェクト計画書.md) |
| 全体構成 | [全体基本設計](設計書一覧/02_基本設計/01_全体基本設計書.md) |
| Frontend | [Frontend基本設計](設計書一覧/02_基本設計/02_Frontend基本設計書.md) |
| API・データ・評価 | [Backend基本設計](設計書一覧/02_基本設計/03_Backend基本設計書.md) |
| ローカルBackend | [Backend README](backend/README.md)・[ADR-003](docs/ADR-003-local-backend-foundation.md) |
| P0〜P7実装工程 | [実装計画](AI面接練習Webアプリ｜実装計画.md)・[P1検証記録](docs/BACKEND_P1_VERIFICATION.md) |
| Terraform・AWS | [Infrastructure基本設計](設計書一覧/02_基本設計/04_Infrastructure基本設計書.md) |
| 次工程の判断 | [決定事項・未確定事項](設計書一覧/04_横断仕様/06_決定事項_未確定事項.md) |

詳細設計は設計書一覧のFrontend／Backend／Infrastructureから参照できます。
既存のAPI・復旧を基準にし、全POSTの冪等性・評価取得契約をBackend側へ反映します。

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
- [Storybook](frontend/stories/): ComponentsはAtoms／Molecules／Organisms／Templates、画面ContainerはPagesに分類。
- [Story Fixture](frontend/stories/fixtures/index.ts): UUID・日時・Session・Evaluation・Feedback・回答100／500／501文字と一般表示用長文の決定的Fixture。
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


## 現在地・更新時の確認

- Frontendは認証なしMSW単体MVP。ローカルBackend（メモリ＋Fake）は追加済みで、Frontendとは未接続です。
- backend/src/interview_backend/にapi・application・models・repositories・evaluation・assetsを配置しています。
- contracts/backend-fixtures.jsonをPython HandlerとFrontend Zodの双方で検証します。
- 認証・実AI・永続化Backend・履歴・PWA・AWS公開は次工程です。
- 接続準備完了は実API接続完了ではありません。非同期起動・障害回復・物理設計を先に確定します。
- Frontend／Backend GitHub Actionsの検証workflowは実装済み。Terraformを含む全体CI/CD・デプロイは未確定です。
- WebPの実寸法と512px期待値に既知の不一致があります。期待値変更・除外で隠しません。
- frontend/skills/は補助資料。一部に他プロダクトの例があり、[AGENTS.md](frontend/AGENTS.md)を優先します。
- API変更時はSchema・API契約・設計書・テストを合わせて確認します。
- 採用判断は最新ADRを参照し、文書追加・変更時は入口と相互リンクも確認します。
- 外部仕様は実装時に公式確認し、未確定事項を推測で埋めません。
