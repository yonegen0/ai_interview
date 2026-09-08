---
document_id: DD-FE-002
title: "Frontend詳細設計 FE02 画面・UI・UX設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 画面設計方針

- USERはスマホ最優先
- ADMINはPC中心
- 1問3分を阻害する説明を置かない
- AI feedbackは短くする
- 「次へ」を最も分かりやすくする
- 小型端末・文字拡大時はスクロール許容

# 2. USER Navigation

Bottom Navigation:
- 練習
- 履歴
- お気に入り

ログイン画面では非表示。

# 3. Login

## Step 1
- Logo/Title
- Email input
- 「認証コードを送る」

## Step 2
- 送信先を一部マスク表示
- OTP input
- 「ログイン」
- 「コードを再送」

セキュリティ上、未登録メールであることを明示しない。

# 4. Practice State Machine

```text
CATEGORY_SELECT
  ↓
QUESTION
  ↓ submit
SUBMITTING
  ↓ success
FEEDBACK
  ↓ next
QUESTION
```

例外:
- OFFLINE
- DAILY_LIMIT
- API_ERROR
- QUESTION_VERSION_ERROR

# 5. Category Select

カテゴリ例:
- 転職理由
- 志望動機
- 自己PR・強み
- 仕事経験
- 困難・失敗
- キャリアプラン
- 逆質問

「おまかせ」追加は将来候補。MVPではカテゴリ指定を基本とする。

# 6. Question画面

表示:
- Category
- Question
- Textarea
- CharacterCounter
- Submit

入力:
- API minimum 1文字
- UI推奨100〜300文字
- API maximum 2000文字

100文字未満でも警告扱いにせず送信可能。

# 7. Feedback画面

優先順:
1. Rating
2. 良かった点
3. 改善ポイント
4. ブラッシュアップ回答
5. Favorite
6. 次へ

長い説明、挨拶、総評は表示しない。

# 8. Submitting

- 送信Button disabled
- 二重タップ防止
- 短いLoading表示
- 画面遷移させない
- practiceIdは送信開始前に生成済み

# 9. API Error

メッセージ例:
- 通信エラー: 「通信できませんでした。接続を確認してください。」
- AI障害: 「評価を取得できませんでした。」
- Processing: 「回答を処理中です。少ししてから結果を確認してください。」
- Failed: 「評価を完了できませんでした。新しくやり直してください。」
- Daily limit: 「本日の練習上限に達しました。」
- Version mismatch: 「アプリが更新されています。再読み込みしてください。」
- Account disabled: セッションを終了しログイン画面へ戻す

Retry UX:
- HTTP timeout / response lost後の「結果を再確認」は同一`practiceId`
- `PRACTICE_PROCESSING`でも新IDを発行しない
- `PRACTICE_FAILED`確定後に「新しくやり直す」を押した場合のみ新`practiceId`

AI POSTは自動retryしない。ユーザー操作によるTransport RetryとNew AttemptをUI上でも分ける。

# 10. History

カード:
- 日時
- Category
- Question要約
- Rating
- Favorite

詳細はAccordion/Drawerで展開。

初期ロード:
- 20件程度
- cursor pagination

# 11. Favorites

履歴と同じCardを基本にする。
面接直前の復習用途のため、改善回答を1タップで展開できる。

# 12. Admin User List

Desktop table:
- 氏名
- Email
- 累計
- 最終練習
- Status
- 詳細

Mobile adminは最低限崩れないがPC最適化を優先。

# 13. Admin Detail

Drawer推奨:
- Profile
- 累計
- 今週
- Favorite count
- History

URL query `?userId=`と同期し、再読み込みで対象を復元可能にする。
`useSearchParams()`を使うClient Componentは`Suspense`境界配下に置き、Static Exportのproduction buildでCSR bailoutエラーを起こさない。

# 14. Responsive

重点:
- 375x667
- 390x844
- 430x932

CSS:
- `min-height: 100dvh`
- safe area
- sticky/footer使用時はsoftware keyboardを考慮

# 15. Accessibility

- labelとinputを関連付け
- Error messageをaria-describedby
- Focus可視化
- 色だけでRating/Errorを表現しない
- タップ領域44px程度
- Text zoomで操作不能にしない
- prefers-reduced-motionを尊重

---

## 参照公式ドキュメント

- [Next.js - Progressive Web Apps](https://nextjs.org/docs/app/guides/progressive-web-apps)
- [Next.js - useSearchParams](https://nextjs.org/docs/app/api-reference/functions/use-search-params)
- [MUI - Next.js integration](https://mui.com/material-ui/integrations/nextjs/)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

