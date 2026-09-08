---
name: indigo-glass-restyle
description: 既存のコンポーネントを biz-karte の Indigo × Glassmorphism デザイン言語に揃える。styled() と src/lib/theme.ts のパレットだけを使い、半透明背景・backdrop-filter ぼかし・primary 色のグロー・borderRadius 12〜20px の柔らかい角丸を統一する。ユーザーが「スタイリッシュにして」「デザインを統一して」と要求したとき、または既存パーツが平板で他画面と浮いているときに使う。
---

# Indigo × Glassmorphism Restyle Skill

このスキルは biz-karte 全体の **Indigo × Glassmorphism** の見た目を、既存の React/MUI コンポーネントに後付けするためのチェックリスト。

## 前提・規約

- スタイルは必ず `styled()` で定義する。`sx` プロパティの常用は禁止（CLAUDE.md）。
- 色は必ず `theme.palette` から取り、ハードコードしない。
- 透明度合成は `alpha(theme.palette.X.main, 0.NN)` を使う。
- 既存の JSDoc・型・公開 API・アクセシビリティ（`useId` / `htmlFor` など）は壊さない。
- デザイン以外（ロジック・props 名・イベントハンドラ）は変更しない。

## パレット早見表（`src/lib/theme.ts`）

- **Indigo（主役・ボタン枠・フォーカスグロー）**
  - `primary.main`: `#3f51b5`（アクセント・グロー基色）
  - `primary.light`: `#7986cb` / `primary.dark`: `#283593`
- **Pink（強いアクセント。控えめに使う）**
  - `secondary.main`: `#ec4899` / `secondary.dark`: `#db2777`
- **テキスト**
  - `text.primary`: `#0f172a` / `text.secondary`: `#475569`
- **背景**
  - `background.default`: `#f1f5f9`（ページ）/ `background.paper`: `#ffffff`（カード）
- **グレー（枠・無効状態）**：`theme.palette.grey[300/400/500]`

## 共通の見た目レシピ

### 1. ガラスパネル（既存 `atoms/Panel.tsx` 参照）

```ts
border: `1px solid ${alpha(theme.palette.primary.main, 0.12)}`,
borderRadius: 20,
backgroundColor: alpha(theme.palette.common.white, 0.72),
backdropFilter: "blur(12px)",
boxShadow: `0 8px 32px ${alpha(theme.palette.primary.main, 0.10)}`,
```

xs では `padding` / `backdropFilter` / `boxShadow` / `borderRadius` を弱めて軽量化する。

### 2. 入力フィールド（既存 `atoms/Input.tsx` 参照）

```ts
"& .MuiOutlinedInput-root": {
  borderRadius: "12px",
  backgroundColor: alpha(theme.palette.common.white, 0.9),
  backdropFilter: "blur(10px)",
  "& fieldset": { borderColor: theme.palette.grey[300] },
  "&:hover fieldset": { borderColor: theme.palette.grey[400] },
  "&.Mui-focused": {
    backgroundColor: theme.palette.common.white,
    boxShadow:
      `0 0 15px ${alpha(theme.palette.primary.main, 0.3)}, ` +
      `inset 0 0 10px ${alpha(theme.palette.primary.main, 0.1)}`,
    "& fieldset": { borderWidth: "1px", borderColor: theme.palette.primary.main },
  },
},
"& .MuiInputLabel-root.Mui-focused": {
  color: theme.palette.primary.main,
},
```

### 3. ボタン（既存 `atoms/Button.tsx`）

共通 `Button` をそのまま使う。`color` 指定でグロー色が連動する（`primary` / `secondary` / `success` / `error` 等）。独自にスタイリングしない。

### 4. 見出し・タイポ

- フォントは `Inter`（`theme.typography.fontFamily`）。MUI Typography variant をそのまま使う。
- 数値表示は `MetricValueText`（`formatMetricValue` で単位整形）を経由する。

### 5. 状態チップ

- レポート状態：`StatusChip`（`draft` / `confirmed` / `superseded`）
- 診断重要度：`SeverityChip`（`info` / `watch` / `alert`）

新規 `styled()` を作らず、既存アトムをそのまま使う。

### 6. テーブル

DataGrid は未導入。テーブルが必要な場合は MUI の `Table` を `styled()` で薄く装飾する：

- ヘッダー：`backgroundColor: alpha(primary.main, 0.06)`
- hover 行：`backgroundColor: alpha(primary.main, 0.04)`
- セル：枠は `theme.palette.grey[300]`

### 7. ローディング・空・エラー

- ローディング：`molecules/LoadingSpinner`（react-spinners の `RingLoader`）
- 空：`molecules/EmptyState`（メッセージ＋CTA）
- エラー：`molecules/ErrorState`（再試行ボタン同梱）

独自実装せず、既存モルキュールを使う。

## 適用フロー（このスキルを呼ばれたとき）

1. 対象ファイルを Read し、`styled()` ブロックを洗い出す。
2. `src/lib/theme.ts` を Read（記憶よりも現状を信用する）。
3. `Panel.tsx` / `Input.tsx` / `Button.tsx` のうち、対象に近い既存パターンを参照する。
4. 修正計画を箇条書きで提示する：
   - 各 `styled()` の何を、なぜ変えるか
   - 新設する `styled()` の役割
   - `sx` を含むコードがあれば `styled()` への置換方針
   - JSDoc や props は触らない旨を明記
5. ユーザーの同意を得てから実装する（無断で実装しない）。
6. 実装後は `npx tsc --noEmit` と `npm run lint` でエラーゼロを確認する。

## やってはいけないこと

- `sx` プロパティで色や余白を当てる。
- カラーコード（`#3f51b5` 等）を直書きする。
- `theme.palette.X.main` 以外の独自パレットを足す。
- 既存の `props` を破壊変更する／JSDoc を消す。
- グロー・ぼかしを付けすぎてゴテゴテにする（**Glass は軽さの演出**）。
- 共通アトム（`Button.tsx` / `Input.tsx` / `Panel.tsx` / `StatusChip.tsx` 等）を改造する。

## 参照すべき既存実装

- `src/lib/theme.ts` — パレットの単一の真実。
- `src/components/atoms/Panel.tsx` — glassmorphism パネルの基盤。
- `src/components/atoms/Button.tsx` — グローボタンの基盤。
- `src/components/atoms/Input.tsx` — グラス入力フィールドの基盤。
