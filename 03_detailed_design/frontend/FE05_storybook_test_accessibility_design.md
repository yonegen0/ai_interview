---
document_id: DD-FE-005
title: "Frontend詳細設計 FE05 Storybook・テスト・アクセシビリティ設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. テスト戦略

```text
Static analysis
  ├─ ESLint
  └─ TypeScript
Component/Story
  └─ Storybook + Vitest Browser
Application E2E
  └─ Playwright
AWS Integration
  └─ dev環境 smoke/manual
```

# 2. Storybook

Framework:
`@storybook/nextjs-vite`

API mock:
- MSWを第一候補

Module mock:
- Storybook公式Module Mock / `sb.mock`

独自Vite PluginでHook差し替えは原則禁止。

# 3. 必須Stories

## QuestionCard
- Default
- LongQuestion
- AlmostCharacterLimit
- MaxCharacterLimit

## FeedbackCard
- RatingS
- RatingA
- RatingB
- RatingC
- LongFeedback

## PracticeSession
- CategoryState
- QuestionState
- SubmittingState
- FeedbackState
- ApiErrorState
- PracticeProcessingState
- PracticeFailedState
- DailyLimitState
- AccountDisabledState
- OfflineState
- QuestionVersionErrorState

## Login
- EmailState
- OtpState
- ErrorState
- SubmittingState

# 4. Browser Mode

- Vitest
- Playwright provider
- Chromium
- headless CI

# 5. Interaction Test

例:
- Answer入力でcounter更新
- 0文字Submit不可
- 1文字Submit可
- Submittingで二重クリック不可
- FeedbackのNextで次Questionへ
- Favorite toggle
- Daily limitでSubmit不可
- Transport Retryで同一`practiceId`を再利用
- `PRACTICE_FAILED`後のNew Attemptで新`practiceId`
- `ACCOUNT_DISABLED`でLogout stateへ遷移

# 6. Playwright E2E

Frontend E2EではCognito/APIをnetwork mockし、UI導線を安定テストする。

主要ケース:
1. Login
2. Practice
3. Feedback
4. History
5. Favorite
6. Admin list/detail
7. Offline cache
8. IndexedDB owner sub不一致を表示しない
9. IndexedDB expiry後はcacheを表示しない
10. Admin `?userId=` routeをStatic build/Navigationで確認
11. 404/Static route

AWS実接続はdev環境Smoke Testとして分ける。

# 7. Viewport

必須:
- 375x667
- 390x844
- 430x932
- Desktop admin 1440x900程度

# 8. Accessibility

Story/Playwrightで最低限確認:
- form label
- focus order
- keyboard operation
- aria error
- color contrast
- text zoom
- reduced motion
- 44px target

# 9. Snapshot

大量のDOM snapshotは原則使用しない。
Visual Regression導入はMVP後の選択肢。
意味のあるinteraction/assertionを優先。

# 10. CI Gate

最低限:
```bash
npm run lint
npm run typecheck
npm run build
npm run build-storybook
npx vitest
```

E2EはCI時間を見てmain branchまたはpre-release gateで実行する。

---

## 参照公式ドキュメント

- [Storybook - Next.js with Vite](https://storybook.js.org/docs/get-started/frameworks/nextjs-vite/?renderer=react)
- [Storybook - Vitest addon](https://storybook.js.org/docs/writing-tests/integrations/vitest-addon)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

