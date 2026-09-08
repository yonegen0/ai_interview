---
document_id: DD-FE-004
title: "Frontend詳細設計 FE04 PWA・オフラインキャッシュ設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 目的

通信が不安定な電車内でも、アプリ起動と過去の復習を可能にする。
AI評価自体はオンライン必須とする。

# 2. PWA構成

- `src/app/manifest.ts`
- `public/sw.js`
- HTTPS
- installable icons

# 3. Cache Storage対象

Cache-first候補:
- Next.js静的JS/CSS
- icons
- static question bank

Network-first候補:
- HTML navigation

禁止:
- Authorization header付きAPI responseの無差別cache
- `/v1/practices` POST
- OTP
- Cognito auth response
- JWT

# 4. Service Worker Version

```js
const CACHE_VERSION = "app-v1";
```

deployごとに更新可能にする。

activate:
- 旧static cache削除

# 5. `sw.js` Header

CloudFrontでService Workerに対して更新を妨げないCache-Controlを設定する。

推奨:
```http
Cache-Control: no-cache, no-store, must-revalidate
```

# 6. Question Bank

URL例:
```text
/question-bank/questions-v1.json
```

Frontend bundleへ直接importする場合でも、
`questionBankVersion`を定数として持つ。

古いPWAとBackend version不一致時:
- Backend `QUESTION_BANK_VERSION_UNSUPPORTED`
- UIでReload促進
- Service Worker update check

# 7. IndexedDB Schema

DB:
`interview-training-cache`

Object Stores:

## practices
Key:
`{sub}:{practiceId}`

Indexes:
- `byCreatedAt`
- `byFavorite`
- `byExpiresAt`

保存項目:
- practiceId
- questionId
- category
- question
- answer
- rating
- goodPoint
- improvement
- improvedAnswer
- favorite
- createdAt
- lastAccessAt
- expiresAt

## metadata
- ownerSub
- cacheSchemaVersion
- questionBankVersion
- lastSyncAt
- lastCleanupAt

JWT / OTP / Cognito auth responseはIndexedDBへ保存しない。

# 8. User Isolation

DB record keyへCognito `sub`を含める。

表示前提:
- 認証済みcurrent subが取得できること
- recordのsub/metadata ownerSubがcurrent subと一致すること

Cleanup:
- ログアウト時: current subの`practices` cacheを削除
- 未認証起動時: 個人履歴を画面へ出さない
- ログイン時: ownerSub不一致データを削除してから表示
- `ACCOUNT_DISABLED`受信時: current subのcacheを削除してLogout

別ユーザーの履歴を一瞬でも表示しない。

# 9. 保持件数

MVP初期値:
- 直近50件を件数上限の目安とする
- Favoriteも個人情報を含むため無期限保持しない
- 全cache entryは最終アクセスから30日で期限切れ

Cleanup trigger:
- app起動時
- login成功時
- history/favorites同期後
- logout時

`expiresAt`超過entryは削除する。
保持日数/件数は定数化し、将来の運用判断で変更可能にする。

# 10. Sync

Online:
```text
API GET
↓
UI
↓
IndexedDB upsert
```

Offline:
```text
API失敗
↓
IndexedDB
↓
Offline Badge
```

# 11. Mutation Offline Queue

MVPでは実装しない。

Offline中:
- Favorite変更はdisabledまたはUI上で「接続後に変更」
- AI回答送信不可

複雑な競合解決を避ける。

# 12. Cache Migration

IndexedDB Schema Versionを持つ。
破壊的変更時はMigrationまたはキャッシュクリアを行う。
DynamoDBが正データなのでCache削除は許容できる。

ユーザー操作として「この端末の履歴データを削除」を提供する。
実行時はcurrent subのIndexedDB practice cacheのみ削除し、DynamoDB上の履歴は削除しないことをUIで明示する。

# 13. PWA更新UX

新version検出時:
- セッションを無理に中断しない
- Feedback表示後など安全なタイミングで「更新する」を提示
- Question Bank unsupported時は即時更新を促す

---

## 参照公式ドキュメント

- [Next.js - Progressive Web Apps](https://nextjs.org/docs/app/guides/progressive-web-apps)
- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

