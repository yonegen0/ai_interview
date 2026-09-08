---
name: hooks-review
description: biz-karte のカスタム Hook 単体を、CLAUDE.md 規約・React Query v5 公式仕様・設計書（基本設計書／詳細設計書）の API 契約と突き合わせてレビューする。対象は `src/features/<feature>/queries.ts`（サーバー状態）／ `src/features/<feature>/hooks.ts`（ローカル状態）／ `src/hooks/*.ts`（横断）のいずれか 1 ファイル。境界は Hook 単体（入力引数・戻り値・`features/<feature>/api.ts` 呼び出し・`qk.*` 無効化）に限定し、ページ／Organism／Atom／Molecule／Storybook ストーリー本体／E2E は対象外。
---

# hooks-review

biz-karte のカスタム Hook を単体でレビューするための専用スキル。

## 使い方

ユーザーが対象 Hook の絶対パスを 1 つ提示する。引数が無ければ `Which hook file?` と聞き返す。
パスを受け取ったら以下を順に実行し、最後に **Findings 表** と **総合判定（マージ可 / 修正後マージ可 / 大幅修正）** を出力する。

## 対象ファイルの分類（最初に判定する）

biz-karte は状態の性質ごとに置き場を分けている。レビュー観点も置き場で切り替える。

| 種別 | パス | 主目的 | 主観点 |
| --- | --- | --- | --- |
| サーバー状態フック | `src/features/<feature>/queries.ts` | `useQuery` / `useMutation` | React Query 規約、`qk.*` 整合、API 契約、エラー写像 |
| ローカル状態フック | `src/features/<feature>/hooks.ts` | `useState` / `useReducer` / `useSearchParams` 周辺 | 責務分離（サーバー状態を持っていないか）、URL 同期、メモ化 |
| 横断共通フック | `src/hooks/*.ts` | 全画面共通の振る舞い（`usePolling` / `useMetricDefs` 等） | 汎用性、副作用クリーンアップ、Context 依存の明示 |

**最重要の責務分離**：

- `queries.ts` に `useState` でローカル UI 状態を抱え込んでいたら High。
- `hooks.ts` の中で `useQuery`/`useMutation` を呼んでいたら High（`queries.ts` へ移すべき）。
- フィルタ・期間・`granularity` を `useState` で持っていて `useSearchParams` 同期されていなければ Medium（CLAUDE.md：「リロード・共有・ブラウザバックで再現したい選択状態は URL 同期」）。

## スコープ（厳守）

- **対象**: 渡された Hook ファイル 1 つ。
  - 公開シグネチャ（引数 / 戻り値型 / オプション型）
  - 内部 state / メモ化 / 依存配列
  - `useQuery` / `useMutation` の設定とキャッシュ無効化
  - `features/<feature>/api.ts` の関数の入出力ペイロード形式
  - エラー写像（`ApiError.code` → UI 状態）
  - 入力バリデーション
  - 対応する Storybook stub (`.storybook/mocks/<hookName>.stub.ts` 等) のシグネチャ整合
- **対象外**（指摘しない）:
  - Hook を呼ぶ Page / Organism の実装
  - Atom / Molecule の見た目（`sx` 禁止違反等）
  - Storybook ストーリー本体（stub のシグネチャ整合は対象に含む）
  - E2E / 視覚回帰
  - サーバー側（API Gateway / Lambda / DynamoDB）の内部実装（**設計書に書かれた I/O 契約の一致のみ** 対象）
  - 直接関係のない他 Hook の改善提案

スコープを越える指摘は「Out of Scope (参考)」として 1 セクションにまとめ、本編の Findings には混ぜない。

## 事前読み込み（並列）

1. レビュー対象 Hook ファイル全文。
2. 同じディレクトリの兄弟ファイル（`features/<feature>/api.ts` / `queries.ts` / `hooks.ts` / `types.ts`）を全部。
3. `src/lib/apiClient.ts`（共通 HTTP クライアント・Authorization 付与経路）。
4. `src/lib/apiError.ts`（`ApiError` / `ApiErrorCode` / `ApiErrorException` / `isApiError`）。
5. `src/lib/queryKeys.ts`（`qk.*` ファクトリ）。
6. 対応する `.storybook/mocks/<hookName>.stub.ts` ／ `.storybook/main.ts` のエイリアス（無ければ「未作成」として指摘）。
7. ルートの `CLAUDE.md`。
8. **設計書**：
   - `基本設計書/基本設計書_経営健康診断システム.md` — 全体像・ドメイン・状態遷移・API 一覧
   - `詳細設計書/00_共通設計.md` — 共通方針
   - 対応する画面の `詳細設計書/0X_*.md`（`Glob` で `詳細設計書/**/*<feature>*.md` を探す）
9. 必要に応じて `src/types/domain.ts`（共通ドメイン型）。

`AGENTS.md` は本リポジトリに存在しないので読まない。

## レビュー観点チェックリスト

各観点を順に確認し、該当があれば Findings に **`file:line` 付き** で記録する。空でも観点名は出力する（「該当なし」を明示）。

### 1. CLAUDE.md 規約

- 先頭 JSDoc（`@file` / `@description`）が存在する。
- `any` 不使用（`type: any` / `as any` / 暗黙 any いずれも）。
- `React.FC` 不使用。
- `import` パスが `@/*` エイリアス（相対 `../../` を避けている）。
- 公開シンボル（型 / 関数）に JSDoc が付いている。
- 推測実装でない（設計書／公式ドキュメント／既存実装に根拠がある）。
- 非推奨 API（後述）を使っていない。

### 2. 責務分離（biz-karte 固有）

- **`queries.ts`** にローカル UI state（モーダル開閉・フォーム下書き等）が混入していない。
- **`hooks.ts`** に `useQuery`/`useMutation` が混入していない。これらは `queries.ts` に置く。
- **`src/lib/` 直下に置かれた Hook は無い**（フックは置かないルール。横断は `src/hooks/`、機能固有は `features/<feature>/hooks.ts`）。
- フィルタ・期間・`granularity` 等の **共有・再現したい選択状態** は `useSearchParams` 経由で、`useState` のみで保持していない。

### 3. シグネチャ設計

- Hook 名が `use` で始まる。
- 引数：**第 1 引数は `storeId: string`**（マルチテナント境界を関数シグネチャに出す既存パターン）。
- 戻り値型を named type で `export` しているか、または React Query の戻り値（`UseQueryResult` 等）をそのまま使うか、判断が一貫している。
- オプション引数は `?:` で省略可能か、デフォルト値の指定箇所が明確か。
- 兄弟 Hook と命名が揃っている（例：`useReportsQuery` / `useConfirmReportMutation` のように `*Query` / `*Mutation` サフィックス）。

### 4. React Query v5 利用（公式: <https://tanstack.com/query/latest/docs>）

- `useQuery`：`queryKey` が `qk.*(storeId, ...)` を使い、自前リテラル配列を組んでいない。
- `useQuery`：`enabled: !!storeId` 相当のガードが入っている（空文字での誤発火を防ぐ）。
- `useMutation`：
  - 型引数 `<TData, TError, TVariables>` が正しい（`TError = ApiError` を期待）。
  - `onSuccess` での `invalidateQueries` 対象が **CLAUDE.md の方針通り「ドメイン接頭辞で一括 invalidate」** になっている。
    - 例：レポート確定・集約・取込完了 → `qk.reports(storeId)`
    - 例：取込ジョブ系の更新 → `qk.imports(storeId)`
    - 例：テンプレート変更 → `qk.metricDefs(storeId)`
  - 複数ドメインを跨ぐ場合は `Promise.all` で並列 `invalidateQueries` → `await` している。
  - `mutateAsync` を使う場合、呼び出し側で例外を捕捉する責務が明確。
- v5 の API 名（`isPending`／`isLoading` 等）の使い分けが一貫している（v5 では `useMutation` は `isPending`、`useQuery` も `isPending`）。
- **非推奨 API を使っていない**：旧オーバーロード（`useQuery(key, fn, options)`）／ `cacheTime`（v5 では `gcTime`）／ `useQuery` の `onSuccess`/`onError`/`onSettled`（v5 で削除済み）。

### 5. 内部 State / メモ化

- `useState` 分割の妥当性。エラー表示は `ApiError` をそのまま保持するのが既定。
- `useCallback` / `useMemo` の依存配列が漏れ・過剰なく揃っている。
- 連打・同一 ID 連続更新時の挙動（`isPending` ガード等）が壊れない。
- 副作用（`useEffect`）にクリーンアップが必要なら正しく書かれている。横断フック（`usePolling` 等）は特にタイマー解除を厳格に。

### 6. 入力バリデーション

- Hook 境界での最低限のガード（空文字 `storeId`、`Number.isFinite`、null）が入っている。
- 値域チェックは サーバ側 1 箇所集約か、UI 即時フィードバックのため Hook でも軽く弾くかが **明示的に意図されている**。
- `trim()` の責務がレイヤー間（フォーム ↔ Hook ↔ api）で重複していない。

### 7. エラー写像（`src/lib/apiError.ts` 参照）

- `ApiError.code` の取り扱いが網羅的：少なくとも `UNAUTHORIZED` / `FORBIDDEN` / `NOT_FOUND` / `CONFLICT` / `VALIDATION` / `SERVER` のうち、その Hook で起こり得るものをカバー。
- `instanceof ApiErrorException` または `isApiError(e)` でない例外時のフォールバック経路がある。
- 各コードと CLAUDE.md の「共通エラー処理」表（401→/login、403→権限なし、404→空、409→再取得、422→項目別、5xx→再試行）が矛盾していない。
- 409（`CONFLICT`）後のリカバリ（最新再取得・再試行）コールバックが Promise を await している。

### 8. API 契約整合（**設計書突き合わせ**）

- `features/<feature>/api.ts` のリクエスト形・レスポンス形が、`基本設計書/基本設計書_経営健康診断システム.md` の API 一覧および対応する `詳細設計書/0X_*.md` の定義と一致。
- パスに `storeId` が含まれている（CLAUDE.md：`storeId` は各 API パスに含める）。
- `apiClient` を経由しており、Authorization ヘッダを自前で組んでいない（Cognito ID トークン付与は `apiClient` の責務）。
- 設計書で「生データを保持しない／AI 入力は集約指標のみ」とされている場合、Hook が生データを取得・保持しようとしていない。
- 設計書で状態遷移が定義されている場合（ImportJob：`uploaded → … → raw_purged`、Report：`draft → confirmed → superseded`）、ポーリング停止条件や invalidate タイミングが整合している。

### 9. Storybook Stub 整合（`.storybook/main.ts` の Vite プラグインで差し替え）

- `.storybook/mocks/<hookName>.stub.ts`（または `<topic>.stub.ts`）が存在する。
- スタブの export 名 / 戻り値プロパティが本 Hook と一致。
- `.storybook/main.ts` のプラグイン／エイリアスに登録されている。
- 無い場合は High 指摘（プラグイン登録漏れも併せて要追加）。

### 10. 認可・ロール

- CLAUDE.md の「権限による出し分け」に従い、Hook 自体は権限判定をしない（UI 側で `useAuthClaims().role` を見て描画／非活性を切る）。Hook 内に `role === 'admin'` などのハードコードがあれば指摘。
- ただし API 側の認可に依存する前提（多層防御）であり、Hook は失敗時の `FORBIDDEN` 表示経路を持つ。

### 11. ポーリング（該当時のみ）

- 取込・診断生成の進捗監視は **`src/hooks/usePolling`** を使う。`setInterval` を直書きしていれば High。
- 間隔（既定 2.5 秒）／完了条件（`aggregated`／`raw_purged`／`completed`）／失敗条件（`failed`）／タイムアウト（取込 3 分・診断 2 分）が CLAUDE.md と整合。

### 12. 非機能

- ログ / `console.*` を本番経路に残していない。
- `as` キャストが必要最小限。
- スタイル関連の混入が無い（Hook なので原則 UI 触らない）。

## 出力フォーマット

```
# Review: <hook file relative path>

## 分類
- 種別: server-state hook / local-state hook / cross-cutting hook
- 対応機能: <feature 名>
- 対応設計書: <参照した設計書のパス>（無ければ "設計書未確認"）

## Findings

| # | Severity | file:line | 観点 | 指摘 | 根拠 | 提案 |
|---|----------|-----------|------|------|------|------|
| 1 | High     | …         | …    | …    | …    | …    |

## 観点別サマリ
1. CLAUDE.md 規約: ✓ / 指摘あり
2. 責務分離: …
3. シグネチャ設計: …
4. React Query: …
5. State / メモ化: …
6. 入力バリデーション: …
7. エラー写像: …
8. API 契約整合: …
9. Storybook Stub: …
10. 認可・ロール: …
11. ポーリング: …
12. 非機能: …

## Out of Scope (参考)
- （Hook の責務を越えるが気付いた点を 1〜3 件まで。無ければ "なし"）

## 総合判定
**マージ可 / 修正後マージ可 / 大幅修正** — 一行コメント
```

## 重大度の基準

- **High**：規約違反（`any` / `React.FC`）、API 契約不一致、`qk.*` 無効化漏れ／誤対象、責務分離違反（`queries.ts` にローカル state、`hooks.ts` に Query/Mutation）、競合時にデータ不整合、stub 未作成、`setInterval` 直書き（`usePolling` 不使用）、非推奨 React Query API の使用。
- **Medium**：バリデーション網羅性不足、エラー写像漏れ、依存配列ミス、命名の不揃い、URL 同期すべき選択状態を `useState` で持っている。
- **Low**：JSDoc 文言、state 分割の好み、メモ化の過不足（性能影響軽微）。

## やってはいけないこと

- 対象 Hook を **編集しない**（読み取り専用レビュー）。レビュー結果のみ出力する。
- 推測でコードを書かない。設計書 / 公式ドキュメント / 既存兄弟ファイルを根拠にする。
- Page / Organism / Atom / Molecule への波及指摘を Findings 表に混ぜない（Out of Scope 欄へ）。
- 設計書が見つからない場合は「設計書未確認」と明示し、API 契約照合は `features/<feature>/api.ts` ↔ `apiClient` ↔ 既存 queryKey の自己整合に留める。
