# Frontend作業ルール

AI面接練習WebアプリのFrontend単体MVP。詳細はルートのdocs/FRONTEND_API_CONTRACT.mdを参照。

## 構成

- Next.js Static Export。Page/LayoutはServer Component、操作はClient Feature。
- app → Feature Page → Template → Organism → Molecule → Atom の依存方向。
- Feature固有Componentは `features/<feature>/components/` 内でAtomic Design階層へ分ける。
- 下位Atomic層から上位層を参照しない。共通ComponentはFeatureを参照しない。
- Next.jsの `app/**/page.tsx` はRoute Entry、Feature内の `components/pages` は画面Containerとして区別する。
- Storybookは `Components/Atoms|Molecules|Organisms|Templates` と `Pages/<feature>` に分類する。
- API Client以外からfetchしない。API Schemaはsrc/lib/api/schemasが唯一の定義元。
- 通信はTanStack Query、入力はReact Hook Form＋Zod、操作段階はReducer。
- MockはMSW。Next.js API Routes、別プロダクト向けhooks stubは使用しない。
- @/* は ./src/*。テーマはsrc/theme。
- 既存のユーザー変更を保持する。

## 規約

- スタイルはMUI styled。sx、React.FC、anyは禁止。
- ファイル冒頭にJSDocで役割を記載。
- 外部仕様は公式ドキュメントを優先。
- Mutation自動Retryは禁止。同じ要求の再確認は同じIdempotency-KeyとPayload。
- 回答や評価をHTMLとして描画しない。

## コマンド

npm run dev:mock / npm run lint / npm run typecheck / npm test
npm run build / npm run build:mock / npm run test:e2e
npm run storybook / npm run build-storybook
