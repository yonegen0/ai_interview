---
document_id: BD-FE-001
title: "AI面接練習Webアプリ MVP 基本設計書（フロントエンド）"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 技術スタック

- Next.js App Router
- TypeScript
- MUI
- TanStack Query v5
- AWS Amplify Auth client module（認証クライアント用途のみ）
- Storybook `@storybook/nextjs-vite`
- Vitest Browser Mode
- Playwright / Chromium
- PWA
- IndexedDB

Amplify HostingやAmplify Backendへの依存を意味しない。Cognito自体はCDKで管理する。

# 2. Next.js運用

```ts
const nextConfig = {
  output: "export",
  trailingSlash: true,
};
```

Server Componentはbuild-timeのみ利用し、ユーザー固有データをruntime server fetchしない。

禁止:
- Server Actions
- runtime cookies
- runtime headers
- dynamic server rendering
- Next.js API Routes/Route HandlerによるBackend API

# 3. 画面

USER:
- `/login`
- `/practice`
- `/history`
- `/favorites`

ADMIN:
- `/admin`
- `/admin/users`

Static Exportのため、詳細は`/admin/users?userId=...`またはDrawerを基本とする。

`useSearchParams()`をClient Componentで利用するStatic Routeは、production buildで必要となるため必ず`<Suspense>`境界配下に置く。URL query読取部分を小さなClient Componentへ分離する。

# 4. データフロー

```text
page.tsx
  ↓
Organism ("use client")
  ↓
Custom Hook
  ↓
TanStack Query
  ↓
shared/api
  ↓
apiClient
  ↓
HTTP API
```

Feature Componentから直接fetchしない。

# 5. コンポーネント責務

## Atoms
表示・小さな操作単位。APIアクセスなし。

## Molecules
Atomsを組み合わせる。基本props駆動。

## Organisms
Custom Hookや状態管理を利用し、UIとロジックの境界になる。

独自ルールとしてAtoms/MoleculesからFeature data-fetch Hookを呼ばない。

# 6. 認証クライアント

`src/shared/auth/`へAWS依存を隔離する。

推奨API:
- `signIn(... preferredChallenge: "EMAIL_OTP")`
- `confirmSignIn`
- `fetchAuthSession`
- `signOut`

Feature側はAmplifyの型/APIを直接参照しない。

# 7. Token Storage

MVP標準:
- AWS Amplify Authの公式Token Providerを利用
- Browser `sessionStorage`を明示設定する
- Tokenを独自Local Storage / IndexedDB / Service Worker Cacheへ複製しない
- タブを閉じた時点でセッションTokenが消えるUXを許容する
- XSS対策としてthird-party script最小化、`dangerouslySetInnerHTML`禁止、依存更新、CSPを併用する

Static Export + MUIではrequestごとのnonceを生成できないため、MVPでStrict nonce CSPは採用しない。
Strict nonce CSPまたはHttpOnly Cookieが必須になった場合は、BFF/Runtime Serverを含むアーキテクチャ変更をADRで行う。

# 8. API Client

`apiClient.ts`:
- Access Token取得
- Authorization header付与
- AbortController timeout
- JSON parse
- HTTP status変換
- `x-request-id`保持
- ApiError化

AI送信POSTはTanStack Queryによる自動retryを行わない。
ただしHTTP timeout / response lost後にユーザーが通信再試行する場合は、**同一`practiceId`**を再利用する。
Backendが`PRACTICE_FAILED`を返した後の「新しい練習」だけ新`practiceId`を生成する。

# 9. Question出題

Frontendはbuild時にCanonical Question Bankから生成されたcurrent versionを利用する。

優先順位:
1. 選択カテゴリ
2. 未回答
3. 直近N問除外
4. ランダム
5. 全問回答済みなら再出題

BackendでquestionId/versionを検証するため、Frontend改ざんだけで任意質問をAI評価させない。
CIでFrontend生成物とCanonical Sourceのversion/hash整合を検証する。

# 10. PWA

- `src/app/manifest.ts`
- `public/sw.js`
- App shell / static asset /生成済みQuestion BankをCache Storage
- 履歴/お気に入りはIndexedDB
- AI POSTやJWTをService Worker cacheへ入れない
- IndexedDBのowner subを認証中subと照合してから表示する
- cache entryは最終アクセスから30日で期限切れ
- ログアウト時・sub不一致時に個人データcacheを削除する

# 11. UI

- Mobile First
- 375×667
- 390×844
- 430×932
- `100dvh`
- safe area考慮
- 主要タップ領域44px程度
- 文字拡大でスクロールを許容

# 12. MUI

- `@mui/material-nextjs`
- `AppRouterCacheProvider`
- Themeを共通化
- `styled()`を基本
- `sx` / inline `style`は禁止（プロジェクトルール）
- Tailwindは使用しない

# 13. テスト

Storybook:
- UI状態
- Error/Offline/Limit
- Mobile viewport

Vitest Browser Mode:
- Story interaction
- Validation
- state transition

Playwright:
- USER主要導線
- ADMIN主要導線
- Static Exportルーティング
- Offline表示

# 14. コーディング規約

- `strict: true`
- `any`禁止
- `React.FC`禁止
- Path Alias `@/* -> ./*`
- TypeScriptファイル冒頭JSDocは既存ルールとして維持
- API/認証依存をFeatureへ漏らさない

---

## 参照公式ドキュメント

- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)
- [Next.js - Progressive Web Apps](https://nextjs.org/docs/app/guides/progressive-web-apps)
- [MUI - Next.js integration](https://mui.com/material-ui/integrations/nextjs/)
- [Storybook - Next.js with Vite](https://storybook.js.org/docs/get-started/frameworks/nextjs-vite/?renderer=react)
- [Storybook - Vitest addon](https://storybook.js.org/docs/writing-tests/integrations/vitest-addon)
- [AWS Amplify - Switching authentication flows](https://docs.amplify.aws/react/frontend/auth/switching-authentication-flows/)
- [AWS Amplify - Tokens and credentials](https://docs.amplify.aws/react/build-a-backend/auth/concepts/tokens-and-credentials/)
- [Next.js - useSearchParams](https://nextjs.org/docs/app/api-reference/functions/use-search-params)
- [Next.js - Content Security Policy](https://nextjs.org/docs/app/guides/content-security-policy)
- [MUI - Content Security Policy](https://mui.com/material-ui/guides/content-security-policy/)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

