---
name: component-style
description: biz-karte の TS/TSX 記述スタイル統一規約。新規ファイル作成・既存ファイル修正時に必ず参照する
---

# 記述スタイル統一規約

`src/components/atoms/Button.tsx` / `Input.tsx` / `Panel.tsx`、`src/components/molecules/Header.tsx` を正とする。

## 共通ルール

| 項目 | ルール |
|---|---|
| クォート | `"` ダブル |
| セミコロン | 文末に付ける |
| 冒頭 | `/** @file <名> @description <責務1行> */` |
| `"use client"` | クライアント実行ファイルのみ、セミコロン付き |
| import 順 | 値 → `import type` で型分離 → `styled` |
| Props | `type FooProps = {...}`、各フィールドに JSDoc |
| 引数 | 分割代入しない `(props: FooProps)` → 中で `props.xxx` |
| styled | `Styled<Name>` 命名、`shouldForwardProp` で `$prefix` を吸収 |
| コンポーネント | 関数頭に JSDoc（`@param props` / `@returns`） |
| export | named export（page.tsx のみ default export） |

## テンプレート（UI コンポーネント）

```tsx
/**
 * @file Foo.tsx
 * @description <このファイルの責務を1〜2行>
 */
"use client";

import Box from "@mui/material/Box";
import { styled } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";

/** Foo の Props */
type FooProps = {
  /** 表示ラベル */
  label: string;
  /** 強調表示するか。省略時は false */
  emphasized?: boolean;
};

/** styled 用の prop */
type StyledRootProps = {
  $emphasized: boolean;
};

/** ルート要素 */
const StyledRoot = styled("div", {
  shouldForwardProp: (prop) => prop !== "$emphasized",
})<StyledRootProps>(({ theme, $emphasized }) => ({
  padding: theme.spacing(1),
  fontWeight: $emphasized ? 700 : 400,
}));

/**
 * <何を表示するか>
 * @param props 表示に必要なプロパティ
 * @returns <返す UI の説明>
 */
export const Foo = (props: FooProps) => {
  return <StyledRoot $emphasized={props.emphasized ?? false}>{props.label}</StyledRoot>;
};
```

## lib/types の例外

- `"use client"` 不要
- Props ルールは対象外（型定義／純粋ロジックのみ）
- 各 export に簡潔な JSDoc を付与

## 禁止事項

- `sx` プロパティの使用（`styled` を使う）
- シングルクォート、セミコロン省略
- props 分割代入（`({ label }: Props)` は禁止）
- JSDoc 省略（@file / Props フィールド / 関数）
