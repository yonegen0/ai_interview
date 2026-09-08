---
document_id: DD-FE-001
title: "Frontend詳細設計 FE01 アーキテクチャ・コンポーネント設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 目的

Frontendの責務境界、ディレクトリ、Component層、依存方向を定義する。

# 2. ディレクトリ

```text
src/
  app/
    layout.tsx
    page.tsx
    globals.css
    manifest.ts
    login/page.tsx
    practice/page.tsx
    history/page.tsx
    favorites/page.tsx
    admin/page.tsx
    admin/users/page.tsx

  features/
    auth/
      components/{atoms,molecules,organisms}/
      hooks/
      model/
    practice/
      components/{atoms,molecules,organisms}/
      hooks/
      model/
    history/
      components/
      hooks/
      model/
    favorites/
      components/
      hooks/
      model/
    admin/
      components/
      hooks/
      model/

  shared/
    api/
    auth/
    lib/
    providers/
    theme/
    constants/
    storage/

resources/
  question-bank/        # Canonical Source

generated/
  question-bank/        # build生成物。手編集禁止

stories/
```

Frontendへ配布するQuestion Bankは`resources/question-bank/`からbuild生成する。

# 3. 依存方向

```text
app
 ↓
features
 ↓
shared
```

禁止:
- `shared -> features`
- Feature AからFeature B内部Componentを直接import
- Atoms/Moleculesから`shared/api`直接呼び出し

Feature間で共通化が必要になったUIは`src/components/atoms`または`shared`相当へ移す。

# 4. Page

`page.tsx`は薄くする。

例:

```tsx
/**
 * @file page.tsx
 * @description 面接練習ページ
 */

import { PracticeSession } from "@/src/features/practice/components/organisms/PracticeSession";

export default function PracticePage() {
  return <PracticeSession />;
}
```

# 5. Component区分

## Atom
- RatingBadge
- CategoryChip
- CharacterCounter
- FavoriteButton
- LoadingIndicator

ルール:
- Data Fetchなし
- Feature Hookなし
- propsで描画

## Molecule
- QuestionCard
- FeedbackSummary
- AnswerExample
- PracticeFooter
- EmptyState

ルール:
- UI Composition
- 原則副作用なし

## Organism
- LoginForm
- PracticeSession
- HistoryList
- FavoritesList
- AdminUserList
- AdminUserDetailDrawer

ルール:
- Custom Hook使用可
- TanStack Query状態とUI状態を調停
- URL/query parameter読取可

## URL Search Params

Static RenderingされるrouteでClient Componentが`useSearchParams()`を呼ぶ場合、production buildでは`Suspense`境界が必要となる。
URL query依存部分を小さなClient Componentへ分離し、page側で以下のように包む。

```tsx
import { Suspense } from "react";

export default function AdminUsersPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AdminUserRouteState />
    </Suspense>
  );
}
```

`useSearchParams()`をpage全体へ無制限に広げない。

# 6. Model

Feature固有型は`features/<feature>/model/`。

例:

```ts
export type Rating = "S" | "A" | "B" | "C";

export type PracticeFeedback = {
  rating: Rating;
  goodPoint: string;
  improvement: string;
  improvedAnswer: string;
};
```

API wire typeとUI modelが異なる場合はMapperを置く。

# 7. Provider

`AppProviders.tsx`:
- ThemeProvider
- QueryProvider
- Auth initialization

`AppRouterCacheProvider`はMUI公式推奨方式でroot layoutに設定する。

# 8. 状態管理

Global state libraryはMVPで追加しない。

- Server state: TanStack Query
- Form/local UI state: React state
- Auth session: Auth client
- Offline cache: IndexedDB repository

複数画面で複雑なClient Global Stateが必要になった時点で再評価する。

# 9. JSDoc

既存ルールとして各TS/TSXファイル冒頭にfile JSDoc。
Exportする主要Component、Hook、API関数に説明を付ける。

# 10. Import

```ts
import { PracticeSession } from "@/src/features/practice/components/organisms/PracticeSession";
```

相対importの`../../../`多用を避ける。

# 11. 禁止事項

- `any`
- `React.FC`
- `sx`
- inline style
- Feature component内fetch
- AWS SDK/Amplify APIをFeatureへ直接露出
- `dangerouslySetInnerHTML`

---

## 参照公式ドキュメント

- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)
- [Next.js - useSearchParams](https://nextjs.org/docs/app/api-reference/functions/use-search-params)
- [MUI - Next.js integration](https://mui.com/material-ui/integrations/nextjs/)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

