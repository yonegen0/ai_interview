# Frontend 開発規約

## 適用範囲と正本

- `frontend/` の変更に適用。ルート[安全規約](../AGENTS.md)を前提とする。
- 依存の採用版は `package.json` と `package-lock.json`、規則は `eslint.config.mjs`・`tsconfig.json` を正本とする。
- UI/APIの詳細契約は [Frontend API契約](../docs/FRONTEND_API_CONTRACT.md) と `src/lib/api/schemas/index.ts` を参照する。
- 原則として既存設計を継承し、規約整理を口実に新層・新依存・大規模リファクタを追加しない。

## 技術・コンポーネント構成

- Next.js 16 App Router、React 19、TypeScript、MUI 9。Static Exportを維持する。
- `next.config.ts` の `output: "export"` を尊重し、Nodeサーバー必須機能・動的Route Handlerへ依存しない。
- `src/app/**/page.tsx` はRoute Entry。Page/Layoutは原則Server Componentとし、イベント処理・ブラウザAPI・認証操作は必要最小限のClient Componentへ分離する。
- Static ExportではServer Componentの処理がビルド時になることを前提に、利用者固有の値やSecretsをビルドHTMLに埋め込まない。
- `app` → Feature Page → Template → Organism → Molecule → Atomの既存依存方向を守る。
- Feature固有のUIは `src/features/<feature>/components/` に置き、必要な場合のみAtomic階層へ整理する。
- Atomic Designを小さな純粋ロジックやAPIコードへ強制しない。下位Atomic層から上位を参照しない。
- 共通UI（`src/components/`）は個別Featureを参照しない。共有化は実際に再利用する場合に限る。
- `src/app` のrouteとFeature内の`components/pages`（画面Container）を混同しない。
- Storybookは `Components/Atoms|Molecules|Organisms|Templates` と `Pages/<feature>` の既存分類に合わせる。
- `@/*` は `./src/*`。デザイントークン・共通テーマは `src/theme/` を正本とする。

## TypeScript・React・見た目

- strictなTypeScriptを維持し、公開境界・props・非同期結果は型を明確にする。
- `any` は原則禁止。未知の外部入力は `unknown` とZod等で狭め、型アサーションで検証を省略しない。
- 既存方針どおり `React.FC` を使用しない。Props型と通常の関数Componentを用いる。
- スタイルは原則MUI `styled`。既存規約の `sx` 禁止を維持し、例外が必要なら既存実装と設計意図を調査する。
- レスポンシブ・スマートフォン優先、フォーカス・ラベル・キーボード操作などのアクセシビリティを守る。
- 色、余白、文字サイズ、Dialog等はテーマと共通UIに統一し、独自値の乱立を避ける。
- 既存規約どおりファイル冒頭にJSDocで役割を記載し、複雑な公開APIには意味のある説明を追加する。
- JSDocを自明なコード全行へ増殖させない。既存ファイルの説明規約を破壊しない。
- ESLintとTypeScriptの細かいルールは設定ファイルを参照し、AGENTS.mdへ再定義しない。

## 状態管理・API

- リモート状態・通信はTanStack Query、フォームはReact Hook Form＋Zod、複雑な画面遷移は既存Reducerを用いる。
- API通信を `src/lib/api/` のClientへ集約し、画面・Hookから直接 `fetch` しない。
- 契約Schemaは `src/lib/api/schemas/index.ts` をFrontendの正本とし、Backendとのfixture・Contractテストで整合を確認する。
- Zodで入力・応答を検証し、APIの例外、Timeout、HTTPエラーを既存の分類で扱う。
- Mutationの自動Retryは禁止。二重送信を抑止し、再確認は同一Idempotency-Keyと同一Payloadを維持する。
- 質問取得・評価ポーリング・結果キャッシュは既存Query Keyと鮮度・復旧設計に整合させる。
- 回答文字数・Coaching V2・STARの制約は実装中の契約を確認し、古い説明文の数値を流用しない。
- Cookieやサーバー専用APIに依存する機能をStatic Export上に無断で追加しない。

## 認証・セキュリティ

- Cognito Email OTP・JWTの既存フローを優先し、認証済みAPI呼出だけに必要なTokenを付与する。
- Token更新、期限切れ、401/403、ログアウト、本人切替は共通の認証状態とキャッシュの整合を保つ。
- USERとADMINの画面上の区別だけを認可とみなさず、Backendの権限検証を前提とする。
- Token、認証情報、本人固有の回答・評価データをログ・URL・静的成果物へ出さない。
- ログアウト／本人切替で前ユーザーのQuery Cache、下書き、復旧情報が表示されないよう確認する。
- 回答・生成文・評価結果はテキストとして描画し、未検証HTMLや危険な`dangerouslySetInnerHTML`を使わない。
- XSS、DOM操作、ブラウザ保存領域、環境変数の公開範囲を変更時に確認する。
- MockはMSWを用い、Mockの認証・データを本番接続と混同しない。

## 品質・検証

- `npm ci` でlockfileに沿って再現可能に準備し、依存更新は必要性・影響・CIを調べてから行う。
- 変更範囲に応じて `npm run lint`、`npm run typecheck`、`npm test` を実施する。
- 必要に応じて `npm run build`、`npm run build:mock`、`npm run test:e2e`、`npm run build-storybook` を実施する。
- Vitestではロジック・UI・契約、Playwrightでは一連の操作、Storybookでは状態別表示を確認する。
- MSW成功・Static Build成功・Playwright Mock成功を実API・Cognito・AWS検証成功として扱わない。
- API契約変更時はFrontend Schema・Backend契約・fixture・関連テストをセットで確認する。
- 認証や回答復旧の変更では、複数タブ・再読み込み・タイムアウト・本人切替の境界条件を確認する。
- 本番用成果物とMock用成果物を区別し、Mockデータの混入を検査する。
- 成功済みテストを再利用する場合はHEAD・依存・入力・実行条件の一致を検証する。
- テスト基準の緩和・失敗のskip化だけで問題を隠さず、原因分析→最小修正→再検証する。

## 公式ドキュメント

- 採用版とlockfileを先に照合し、該当版の公式資料を確認する。脆弱性・変更点は最新の公式情報も確認する。
- Next.js App Router / Static Export: https://nextjs.org/docs/app ｜ https://nextjs.org/docs/app/guides/static-exports
- React: https://react.dev/learn ｜ TypeScript: https://www.typescriptlang.org/docs/
- MUI: https://mui.com/material-ui/ ｜ TanStack Query: https://tanstack.com/query/latest/docs/framework/react/overview
- React Hook Form: https://react-hook-form.com/get-started ｜ Zod: https://zod.dev/
- 公式資料にアクセスできなければ未確認と記録し、単純なローカル整形に不要な外部調査を強制しない。
