# CLAUDE.md

## 情報源ルール

- 外部情報が必要な場合は、必ず公式ドキュメントを最優先で参照すること
- 次に公式 GitHub リポジトリを参照すること
- 不明な場合のみ、外部記事や非公式情報を補助的に参照すること
- 推測だけでコードを書かないこと
- 非推奨 API は使用しないこと
- 参照した情報には、可能な限り出典を明記すること

対象の優先ソース例:

- TypeScript: <https://www.typescriptlang.org/>
- React: <https://react.dev/>
- Next.js: <https://nextjs.org/docs>
- MUI: <https://mui.com/>
- Storybook: <https://storybook.js.org/>
- AWS SDK v3 / S3 / Bedrock: <https://docs.aws.amazon.com/>

## コマンド

```bash
npm run dev          # 開発サーバー起動（Next.js）
npm run build        # プロダクションビルド
npm run lint         # ESLint実行
npm run storybook    # Storybook起動（port 6006）
npx vitest           # Storybookテスト実行（Playwright + Chromium）
npx vitest --reporter=verbose  # テスト詳細表示
```

テストはStorybookのストーリーをvitest + Playwrightでブラウザ実行する構成（`vitest.config.ts`）。

## アーキテクチャ概要

**汎用受付・順番管理システム。** 施設（`facilityId`）単位でチケットを管理し、受付→チェックイン→呼び出し→完了の状態遷移を追跡する。現在はAPIをインメモリモックで実装しており、将来的にAWS（API Gateway + Lambda + DynamoDB）へ切り替える想定。

### ディレクトリ構成

```text
src/
  app/
    api/facilities/[facilityId]/   # API Routesのモック実装（インメモリストア）
    facilities/[facilityId]/       # 各機能のページ（issue/reception/queue/settings/logs）
    layout.tsx / globals.css       # ルートレイアウト
  features/                        # ドメイン機能ごとのモジュール
    ticket-issue/                  # 受付番号発行
    ticket-checkin/                # 受付管理（チェックイン・スキップ・削除、スタッフ + セルフ）
    queue/                         # 順番管理（呼び出し・完了・並び替え・Undo）
    undo/                          # 直前操作の取り消し
    logs/                          # 操作ログ閲覧
    settings/                      # 施設設定
  shared/
    api/                           # fetch関数（ticketApi.ts, logApi.ts, settingsApi.ts）
    lib/                           # apiError.ts, queryKeys.ts
    providers/                     # AppProviders（React Query）
    theme.ts                       # MUIテーマ
  components/atoms/                # 汎用Atoms（MUIラップ）
stories/                           # Storybookストーリー（src/featuresと同じ構造）
.storybook/
  mocks/                           # Hooksスタブ（*.stub.ts）
  main.ts                          # Viteプラグインでhookを自動スタブに差し替え
```

### フィーチャーモジュール内の構成

各フィーチャー（例: `queue/`）は以下の構成を持つ：

```text
components/
  atoms/     # MUIラップなど最小単位
  molecules/ # Atomsの組み合わせ（Storybookで独立してテスト可能）
  organisms/ # hooksを呼び出しUI+ロジックを統合する境界
hooks/       # APIを呼び出すカスタムhooks（React Query）
model/       # 型定義・DTO変換・バリデーション関数
```

### データフロー

ページ（Server Component）→ Organism（`"use client"`）→ hooks → `src/shared/api/`の関数 → Next.js API Routes（`src/app/api/`）

Organisms が hooks を呼び出す唯一の層。Molecules/Atoms はロジックを持たず、propsのみで動作する。

### API接続先（AWS）

API は AWS API Gateway dev stage に接続する。`.env.local` に以下を設定すること（`.env.local.example` を参照）：

```text
NEXT_PUBLIC_API_BASE_URL=https://xxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/dev
```

`src/shared/api/apiBaseUrl.ts` の `buildApiUrl` 関数が全 fetch 呼び出しのベースURLを解決する。Next.js API Routes（モック）は削除済み。

### Storybookのhooksスタブ戦略

`.storybook/main.ts`のViteプラグインが、hooks（`useIssueTicket`等）のimportを`.storybook/mocks/*.stub.ts`へ自動的に差し替える。ストーリー内では`beforeEach`でスタブの返り値を設定する。新しいhooksを追加したらスタブも作成し、`main.ts`のプラグインとエイリアスに登録する。

## コーディング規約

### ファイル形式

全ファイルの冒頭に JSDoc を記述する：

```ts
/**
 * @file FileName.tsx
 * @description 〇〇を表示・提供するコンポーネント/関数
 */
```

### コンポーネント

```ts
/** XxxComponent の Props */
type XxxComponentProps = { ... };

/**
 * 〇〇を表示する
 * @param props 表示に必要なプロパティ
 * @returns 〇〇
 */
export const XxxComponent = (props: XxxComponentProps) => { ... };
```

- `React.FC` は使用しない
- スタイルは MUI の `styled` を使う（`sx` は禁止）
- `any` は使用禁止

### パスエイリアス

`@/*` がプロジェクトルート（`./`）にマップされている。`@/src/features/...` が標準的な import パスとなる。
