# Frontend未コミット差分のファイル別レビュー

F1〜F5は修正済み。[修正内容・回帰テスト・最終検証結果](FRONTEND_REVIEW_FIXES.md)を参照。
以下は修正前のレビュー記録。行番号と再現用6ケースも当時のもの。

2026-10-06。比較元HEAD: `ded1d50cd097fa9fcfd780649608ab74049a4bc5`。
対象はFrontendの未コミット125ファイル（src 69、stories 35、tests 13、設定・説明 8）。
hooks・通信・認証・保存・画面処理を重点確認し、表示部品と試験の変更もファイル別に確認した。
ステージ済み差分はなし。既存の実装ファイルは編集していない。

## 指摘

### F1 — P1: 401再送を要求開始時の利用者に限定する

対象: [src/lib/api/client.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/api/client.ts:99)（99〜105行）。

Aの要求が401を返す前にログアウトし、Bとしてログインすると、`auth.access(true)`はBのtokenを返す。
そのtokenでAのPayloadとIdempotency-Keyをそのまま再送するため、Aの保存・練習開始をBとして実行できる。
認証サービス内のgenerationチェックはrefreshの開始以降だけを保護し、元のAPI要求の利用者までは確認しない。

ローカル再現では最初のPOSTのAuthorizationがA、同じ本文・キーの2回目がBになり、要求が成功扱いになることを確認した。
要求開始時のsub／認証世代を固定し、再送前に同じ利用者・同じ世代かを確認する必要がある。
古い要求の二度目の401で新しいログインをinvalidateすることも防ぐべき。

### F2 — P2: アンマウント後の成功応答で別利用者のpendingを消さない

対象: [src/features/interview/hooks/usePracticeStart.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/hooks/usePracticeStart.ts:81)（81〜82行）。
関連: [useQuestionManagement.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/hooks/useQuestionManagement.ts:111)、[useFeedbackNavigation.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/hooks/useFeedbackNavigation.ts:57)、[scopedKey](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/storage/recovery.ts:26)。

Aの開始POSTを待機させたまま画面を離れ、ログアウトしてBの未確定開始要求を保存する。
その後Aの201応答が返ると、古いhookの`removeSaved`が現在のBのscopeを使い、Bのpendingを削除する。
さらにBの画面をAのsessionIdへ遷移させる。Bの要求を同じキーで再確認できなくなり、再開始で重複Sessionを作る原因になる。

ローカル再現ではhookをunmountした後でもBの保存レコードの削除とAのSessionへのpushを確認した。
操作開始時の保存先と利用者を保持し、古い処理の完了を現在の画面・別利用者の保存先へ適用しないこと。
Queryのcancel/clearだけでは進行中のMutation callbackは止まらない。
管理者保存・次問の成功処理にも同じ呼出時scopeの問題がある。

### F3 — P2: 書込だけが失敗したキーはmemoryの最新データを読む

対象: [src/lib/storage/recovery.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/storage/recovery.ts:36)（36〜40行）。
影響先: [src/mocks/store/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/store/index.ts:62)（62〜63行）。

`save`はsessionStorageへの書込が失敗してもmemoryへ新データを保持する。
一方、`readSaved`はgetItemが例外になった場合にしかmemoryを参照しない。
QuotaExceededErrorではgetItemは成功するため、古いデータまたはnullを返して最新の下書き・未確定要求を復旧できない。

再現では「before quota」を保存した後、setItemだけを失敗させて「after quota」を保存すると、読取は「before quota」に戻った。
Mock Repositoryでも版1への更新後、次のreadで永続領域の版0をmemoryへ戻すことを確認した。
同じタブの画面移動だけでも発生し、Mockの保存成功・冪等記録が巻き戻る。
書込失敗したキーを追跡し、そのキーでは最新memoryを優先する必要がある。

### F4 — P2: 古いQuery Cacheで復旧時の競合を確定しない

対象: [src/features/admin/hooks/useQuestionManagement.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/hooks/useQuestionManagement.ts:42)（42〜54行）。

保存成功時に`admin-question-bank`のQuery Cacheを更新しないため、画面へ戻った直後には前の版がquery.dataとして返る。
復旧effectはその古い版を使って`loaded.current=true`にし、保存済みbaselineとの版違いを競合とする。
後から新しいGETが成功してもloadedがtrueなので判定とcomparisonは更新されない。

再現ではCache=版0、復旧baseline=版1、Backend=版1の状態で、GET完了後もstage=conflict・comparison=版0・disabled=trueが残った。
最新版と一致する保存済みデータでも編集できず、「最新版で編集し直す」が古い本文を採用してしまう。
保存成功時のCache更新と、復旧時の比較に最新GETの結果を使う処理が必要。

### F5 — P2: 旧Mockのrequestsを利用者付きキーへ移行する

対象: [src/mocks/store/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/store/index.ts:70)（70〜87行）。
関連: [src/mocks/handlers/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/handlers/index.ts:115)（115〜116行）。

旧実装は`requests[key]`、新実装はsubとkeyを連結したキーで成功済み要求を検索する。
version1→2のコピーはrequestsを旧キーのまま残すため、同じ利用者が同じキー・本文で再確認しても成功済み記録を参照できない。

再現ではversion1に成功済みの開始要求とSessionを保存し、移行後に同じ開始要求を再送すると別のSessionが作られ、Session数が2になった。
version1原本とfingerprint・保存済み応答を保全しつつ、移行先のrequestsも旧所有者`mock-user`へ対応付ける必要がある。
質問snapshotの補完だけでは旧要求の冪等性は維持されない。

## 検証

| 検証 | 今回の結果 |
|---|---|
| `npm run lint` | 成功 |
| `npm run typecheck` | 成功 |
| `npm run test:unit` | 13ファイル、180件成功 |
| `npm test -- --project storybook` | 44ファイル、373件成功 |
| 指摘のローカル再現 | 6ケースで5件の問題を確認（F3は下書きとMock Storeの2ケース） |
| build / Playwright E2E / 実Cognito・AWS | 今回は未実行 |

既存試験の成功は上記の条件を網羅していない。再現ケースは「現在の誤った挙動が起きる」ことをassertする証跡であり、修正後の合格を示すものではない。
認証はstub/Mock、APIはfetch stub/MSWを使用した。

最初のunit起動はWindows sandboxの子プロセス制限（spawn EPERM）で開始できなかった。
同じローカル試験を制限外で実行し、上記結果を確認した。
StorybookではVite設定と装飾画像のLCPに関する警告が出たが、試験失敗はなかった。

再現用ソースと専用設定はGit管理外の
[frontend/playwright/.cache/review-20261006/review-probes.test.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/playwright/.cache/review-20261006/review-probes.test.tsx) と
[vitest.config.mts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/playwright/.cache/review-20261006/vitest.config.mts) に保存。
通常のtests配下に置いた一時ファイルは削除済み。

`frontend`を作業ディレクトリにして再実行できる。

```powershell
npm exec -- vitest run --config playwright/.cache/review-20261006/vitest.config.mts
```

## ファイル別の確認結果

「指摘なし」は、今回の差分で具体的な追加不具合を確認しなかったことを表す。
「関連」は上記の共通原因の影響先で、別の指摘件数としては数えていない。

### src（69ファイル）

| ファイル | 結果 | 確認内容 |
|---|---|---|
| [src/hooks/useAuthSession.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/hooks/useAuthSession.ts) | 指摘なし | useSyncExternalStoreと初期化の接続、サーバー側snapshotを確認。 |
| [src/hooks/useAuthBoundary.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/hooks/useAuthBoundary.ts) | 指摘なし | 復元中・未認証・ADMIN不足の分岐、戻り先URLを確認。 |
| [src/hooks/useAccountActions.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/hooks/useAccountActions.ts) | 関連 F1/F2 | 利用者変更時のQuery中断・消去は確認。進行中Mutationの遅延応答は別途防御が必要。 |
| [src/lib/auth/cognito.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/auth/cognito.ts) | 指摘なし | EMAIL_OTP選択、challenge応答、refresh/revokeのSDK入力、maxAttempts=1を確認。実AWS未検証。 |
| [src/lib/auth/session.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/auth/session.ts) | 関連 F1/F2 | 認証応答の世代チェック、refresh単一実行、sub一致、タブ内保存を確認。API処理へ世代を連動させていない。 |
| [src/lib/api/client.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/api/client.ts) | F1 / P1 | 401の再送が現在の利用者へ切り替わる。エラーの日本語化、Abort、応答検証も確認。 |
| [src/lib/api/admin.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/api/admin.ts) | 指摘なし | 管理者GET/POSTのSchemaとIdempotency-Keyの受渡しを確認。F1の影響は共通Client由来。 |
| [src/lib/api/interview.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/api/interview.ts) | 指摘なし | full/category/旧形式の開始要求、UUID検査、回答・次問のPayloadを確認。F1の影響は共通Client由来。 |
| [src/lib/api/schemas/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/api/schemas/index.ts) | 指摘なし | 10有効カテゴリ＋旧difficulty、進捗3項目の整合、UTF-16上限、重複UUID、strictな管理入力を確認。 |
| [src/lib/storage/recovery.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/storage/recovery.ts) | F3 / P2・関連 F2 | 書込失敗時のmemoryを通常読取が無視する。利用者scopeの計算が呼出時点の状態に依存する点も確認。 |
| [src/lib/storage/status.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/lib/storage/status.ts) | 指摘なし | 保存不可通知と購読解除を確認。 |
| [src/features/admin/hooks/useQuestionBankEditor.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/hooks/useQuestionBankEditor.ts) | 指摘なし | RHFとZod、FieldArrayの独立fieldKey、追加UUID、範囲内移動、リセットを確認。 |
| [src/features/admin/hooks/useQuestionManagement.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/hooks/useQuestionManagement.ts) | F4 / P2・関連 F2 | 古いQuery Cacheで復旧判定を固定する。確認スナップショット、同じ要求の再確認、409/403分岐も確認。 |
| [src/features/admin/model/editor.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/model/editor.ts) | 指摘なし | 不正入力中の下書きSchema、baseline/pendingの検証、追加・削除・編集・移動の集計を確認。 |
| [src/features/auth/hooks/useEmailOtpLogin.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/auth/hooks/useEmailOtpLogin.ts) | 指摘なし | 送信の単一実行、6桁検査、60秒待機、メール変更、固定エラー表示、戻り先を確認。 |
| [src/features/auth/model/login.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/auth/model/login.ts) | 指摘なし | email検証と戻り先のorigin・pathnameホワイトリストを確認。 |
| [src/features/interview/hooks/usePracticeStart.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/hooks/usePracticeStart.ts) | F2 / P2 | アンマウント後の成功が別利用者のpendingを消す。開始要求の固定・復旧、カテゴリ消失時の再取得も確認。 |
| [src/features/interview/hooks/usePracticeSession.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/hooks/usePracticeSession.ts) | 指摘なし | URL ID、再挑戦元のSession/質問番号一致、Query Abort、contextKeyを確認。 |
| [src/features/interview/hooks/usePracticeController.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/hooks/usePracticeController.ts) | 指摘なし | 評価完了時の一度だけの遷移、RHFの接続、終了確認と破棄の委譲を確認。 |
| [src/features/interview/model/practice.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/model/practice.ts) | 指摘なし | view/form/actionsの型と実際の呼出側の対応を確認。 |
| [src/features/interview/model/practiceStart.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/model/practiceStart.ts) | 指摘なし | 開始画面のview/actionsとAPI選択肢の型の対応を確認。 |
| [src/features/feedback/hooks/useFeedbackResult.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/hooks/useFeedbackResult.ts) | 指摘なし | attemptIdの検査、取得Query、表示分岐へのデータ受渡しを確認。 |
| [src/features/feedback/hooks/useFeedbackNavigation.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/hooks/useFeedbackNavigation.ts) | 関連 F2 | 現在のcompleted AttemptとhasNextによる制御、同じキーの再確認を確認。遅延成功のStorage/Cache/遷移にも利用者ガードが必要。 |
| [src/features/feedback/model/navigation.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/model/navigation.ts) | 指摘なし | 次問・再挑戦・一巡終了の表示状態と操作型を確認。 |
| [src/mocks/store/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/store/index.ts) | F5 / P2・関連 F3 | 旧requestsのキーが新形式へ移行されない。quota時には古い永続Storeでmemoryを戻してしまう。 |
| [src/mocks/handlers/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/handlers/index.ts) | 関連 F5 | 新requestsをsub:keyで識別するため旧キーを参照できない。所有者・ADMIN認可、一巡終了と質問snapshotを確認。 |
| [src/mocks/data/questions.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/data/questions.ts) | 指摘なし | Backendの15問原本と旧21問を分離し、各Schemaで検証することを確認。 |
| [src/mocks/data/legacy-questions.json](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/mocks/data/legacy-questions.json) | 指摘なし | 旧21問の復旧資産。migrationテストによる旧質問・ID・順番の一致を確認。 |
| [src/components/atoms/Actions.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/Actions.tsx) | 指摘なし | 余白のtheme移行と操作部品の配置を確認。 |
| [src/components/atoms/Input.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/Input.tsx) | 指摘なし | TextField propsの透過、ControllerからのinputRef/値/blurの接続を確認。 |
| [src/components/atoms/Panel.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/Panel.tsx) | 指摘なし | themeのpadding/shape/shadow、質問・回答の改行と折返しを確認。 |
| [src/components/atoms/Select.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/Select.tsx) | 指摘なし | useId、ラベル・説明・エラーの関連付け、inputRef/blur/changeの接続を確認。 |
| [src/components/atoms/ChoiceButton.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/ChoiceButton.tsx) | 指摘なし | 選択状態のaria-pressed、buttonの型、disabled/focus/クリックの受渡しを確認。 |
| [src/components/atoms/Text.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/atoms/Text.tsx) | 指摘なし | Typographyのprops、意味を持つ要素、改行と折返しを確認。 |
| [src/components/molecules/AccountActions.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/molecules/AccountActions.tsx) | 指摘なし | hookと表示Componentの接続を確認。 |
| [src/components/molecules/AccountActionsView.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/molecules/AccountActionsView.tsx) | 指摘なし | USER/ADMIN/未認証の導線とログアウトcallbackを確認。 |
| [src/components/molecules/Header.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/molecules/Header.tsx) | 指摘なし | 見出しと説明のtheme typography移行を確認。 |
| [src/components/organisms/AuthBoundary.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/organisms/AuthBoundary.tsx) | 指摘なし | admin設定をhookへ渡し、認証状態に応じた子画面の描画を確認。 |
| [src/components/organisms/AuthBoundaryView.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/organisms/AuthBoundaryView.tsx) | 指摘なし | 復元中・未認証・権限不足では子画面を描画しないことを確認。 |
| [src/components/templates/AppShell.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/components/templates/AppShell.tsx) | 指摘なし | 共通AccountActionsとSuspense、QueryProvider内での利用を確認。 |
| [src/features/admin/components/molecules/QuestionEditorCard.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/molecules/QuestionEditorCard.tsx) | 指摘なし | 本文・カテゴリのController、fieldKeyによるID、disabled、上下移動・削除を確認。 |
| [src/features/admin/components/organisms/QuestionBankConflict.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/organisms/QuestionBankConflict.tsx) | 指摘なし | 最新版・今回の編集・変更前の参照の表示とcallbackを確認。 |
| [src/features/admin/components/organisms/QuestionBankPreview.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/organisms/QuestionBankPreview.tsx) | 指摘なし | 本文・カテゴリ・順番をpropsからテキストで表示することを確認。 |
| [src/features/admin/components/organisms/QuestionBankSaveConfirmation.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/organisms/QuestionBankSaveConfirmation.tsx) | 指摘なし | 変更件数、保存・戻るcallback、button typeを確認。 |
| [src/features/admin/components/organisms/QuestionBankStatus.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/organisms/QuestionBankStatus.tsx) | 指摘なし | loading/saving/success/uncertain/forbiddenの表示と再確認導線を確認。 |
| [src/features/admin/components/organisms/QuestionEditorList.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/organisms/QuestionEditorList.tsx) | 指摘なし | 安定したfieldKey、現在indexの操作、先頭・末尾・空一覧の分岐を確認。 |
| [src/features/admin/components/pages/QuestionManagement.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/pages/QuestionManagement.tsx) | 指摘なし | hookのview/editor/actionsをTemplateへ渡すことを確認。 |
| [src/features/admin/components/templates/QuestionManagementTemplate.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/admin/components/templates/QuestionManagementTemplate.tsx) | 指摘なし | フォームと確認画面の構成、各段階のdisabled、preview/競合部品へのpropsを確認。 |
| [src/features/auth/components/organisms/EmailOtpForm.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/auth/components/organisms/EmailOtpForm.tsx) | 指摘なし | email/codeのRHF接続、入力モード、autocomplete、各段階のdisabledと手動再送を確認。 |
| [src/features/auth/components/pages/LoginPage.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/auth/components/pages/LoginPage.tsx) | 指摘なし | form/view/actionsの接続、submit/resendの受渡しを確認。 |
| [src/features/auth/components/templates/LoginTemplate.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/auth/components/templates/LoginTemplate.tsx) | 指摘なし | ログイン見出しとOTPフォームの合成を確認。 |
| [src/features/interview/components/molecules/PracticeCategorySelector.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/molecules/PracticeCategorySelector.tsx) | 指摘なし | APIから受け取ったカテゴリ・問数の選択表示、callback、disabledを確認。 |
| [src/features/interview/components/molecules/PracticeModeSelector.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/molecules/PracticeModeSelector.tsx) | 指摘なし | full/categoryと選択状態、問数、callbackを確認。 |
| [src/features/interview/components/molecules/QuestionCard.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/molecules/QuestionCard.tsx) | 指摘なし | 質問本文のテキスト描画、カテゴリ、質問番号・全問数の表示を確認。 |
| [src/features/interview/components/organisms/AnswerSubmission.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/organisms/AnswerSubmission.tsx) | 指摘なし | 入力・送信中・未確定の分岐、固定要求の再確認、重複送信抑止を確認。 |
| [src/features/interview/components/organisms/PracticeSelector.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/organisms/PracticeSelector.tsx) | 指摘なし | 選択肢取得エラー、カテゴリ選択、開始可能状態、再確認導線を確認。 |
| [src/features/interview/components/pages/InterviewPractice.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/pages/InterviewPractice.tsx) | 指摘なし | loading/error/再挑戦不一致の分岐、contextKeyによるForm再初期化を確認。 |
| [src/features/interview/components/pages/PracticeSessionContent.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/pages/PracticeSessionContent.tsx) | 指摘なし | ControllerとTemplateの接続、評価Timingの受渡しを確認。 |
| [src/features/interview/components/pages/PracticeStart.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/pages/PracticeStart.tsx) | 指摘なし | 開始hookのview/actionsをTemplateへ渡すことを確認。 |
| [src/features/interview/components/templates/PracticeForm.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/templates/PracticeForm.tsx) | 指摘なし | 回答・評価待機・失敗、終了Dialog、未確定要求を保持して終了する分岐を確認。 |
| [src/features/interview/components/templates/PracticeStartTemplate.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/interview/components/templates/PracticeStartTemplate.tsx) | 指摘なし | 表示構成とPracticeSelectorへのpropsの受渡しを確認。 |
| [src/features/feedback/components/organisms/FeedbackNavigation.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/components/organisms/FeedbackNavigation.tsx) | 指摘なし | 次問・再挑戦・最終問・古い結果・未確定の導線、pending時の無効化を確認。 |
| [src/features/feedback/components/pages/FeedbackResult.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/components/pages/FeedbackResult.tsx) | 指摘なし | 結果取得hook、IDに応じた再初期化、Navigation hookとTemplateの接続を確認。 |
| [src/features/feedback/components/templates/FeedbackResultTemplate.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/features/feedback/components/templates/FeedbackResultTemplate.tsx) | 指摘なし | 結果カードと次の操作の合成を確認。 |
| [src/app/admin/questions/page.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/app/admin/questions/page.tsx) | 指摘なし | 静的Route Entry、SuspenseとADMIN境界を確認。 |
| [src/app/login/page.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/app/login/page.tsx) | 指摘なし | 静的Route EntryとuseSearchParamsを包むSuspenseを確認。 |
| [src/app/practice/page.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/app/practice/page.tsx) | 指摘なし | 静的Route Entry、Suspenseと認証境界を確認。 |
| [src/app/practice/session/page.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/app/practice/session/page.tsx) | 指摘なし | 静的Route Entry、Suspenseと認証境界を確認。 |
| [src/app/result/page.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/src/app/result/page.tsx) | 指摘なし | 静的Route Entry、Suspenseと認証境界を確認。 |

### stories（35ファイル）

| ファイル | 結果 | 確認内容 |
|---|---|---|
| [stories/components/atoms/ChoiceButton.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/atoms/ChoiceButton.stories.tsx) | 指摘なし | 選択・disabled・キーボード操作のStoryを確認。 |
| [stories/components/atoms/Input.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/atoms/Input.stories.tsx) | 指摘なし | email/OTP/質問本文、RHFのエラーとfocusを確認。 |
| [stories/components/atoms/Select.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/atoms/Select.stories.tsx) | 指摘なし | RHF required/focus/説明とPortal選択操作を確認。 |
| [stories/components/atoms/Text.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/atoms/Text.stories.tsx) | 指摘なし | 本文・見出し・status・改行・長文のStoryを確認。 |
| [stories/components/molecules/AccountActions.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/AccountActions.stories.tsx) | 指摘なし | hookを使うUSER/ADMIN/未認証のStoryを確認。 |
| [stories/components/molecules/AccountActionsView.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/AccountActionsView.stories.tsx) | 指摘なし | 表示専用の認証別Storyとcallbackを確認。 |
| [stories/components/molecules/admin/QuestionEditorCard.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/admin/QuestionEditorCard.stories.tsx) | 指摘なし | 本文長・空白・先頭/末尾・disabledのStoryを確認。 |
| [stories/components/molecules/interview/PracticeCategorySelector.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/interview/PracticeCategorySelector.stories.tsx) | 指摘なし | 未選択・選択・空一覧・disabledを確認。 |
| [stories/components/molecules/interview/PracticeModeSelector.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/interview/PracticeModeSelector.stories.tsx) | 指摘なし | full/category/disabledを確認。 |
| [stories/components/molecules/QuestionCard.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/molecules/QuestionCard.stories.tsx) | 指摘なし | 現行＋旧カテゴリの網羅、長文、進捗、狭幅を確認。 |
| [stories/components/organisms/admin/QuestionBankConflict.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/admin/QuestionBankConflict.stories.tsx) | 指摘なし | 比較・取得失敗・旧編集参照・長文を確認。 |
| [stories/components/organisms/admin/QuestionBankPreview.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/admin/QuestionBankPreview.stories.tsx) | 指摘なし | 改行と本文上限のプレビューを確認。 |
| [stories/components/organisms/admin/QuestionBankSaveConfirmation.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/admin/QuestionBankSaveConfirmation.stories.tsx) | 指摘なし | 変更種別別の件数、保存中disabledを確認。 |
| [stories/components/organisms/admin/QuestionBankStatus.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/admin/QuestionBankStatus.stories.tsx) | 指摘なし | 取得・保存・未確定・成功・権限不足を確認。 |
| [stories/components/organisms/admin/QuestionEditorList.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/admin/QuestionEditorList.stories.tsx) | 指摘なし | 0/1/15/100問の表示を確認。 |
| [stories/components/organisms/auth/EmailOtpForm.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/auth/EmailOtpForm.stories.tsx) | 指摘なし | 各入力段階、不正入力、待機、再送、失敗を確認。 |
| [stories/components/organisms/AuthBoundary.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/AuthBoundary.stories.tsx) | 指摘なし | 実hookを使う認証/ADMIN境界のStoryを確認。 |
| [stories/components/organisms/AuthBoundaryView.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/AuthBoundaryView.stories.tsx) | 指摘なし | 表示専用の復元中・期限切れ・権限不足を確認。 |
| [stories/components/organisms/feedback/FeedbackNavigation.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/feedback/FeedbackNavigation.stories.tsx) | 指摘なし | 次問・最終問・古い結果・未確定・エラーを確認。 |
| [stories/components/organisms/interview/AnswerSubmission.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/interview/AnswerSubmission.stories.tsx) | 指摘なし | 回答上限、不正入力、送信中、再確認を確認。 |
| [stories/components/organisms/interview/PracticeSelector.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/organisms/interview/PracticeSelector.stories.tsx) | 指摘なし | full/category、取得失敗、開始中、未確定を確認。 |
| [stories/components/templates/admin/QuestionManagementTemplate.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/templates/admin/QuestionManagementTemplate.stories.tsx) | 指摘なし | 確認・未確定・競合・プレビューと3画面幅を確認。 |
| [stories/components/templates/auth/LoginTemplate.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/templates/auth/LoginTemplate.stories.tsx) | 指摘なし | email/code/errorと3画面幅を確認。 |
| [stories/components/templates/feedback/FeedbackResultTemplate.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/templates/feedback/FeedbackResultTemplate.stories.tsx) | 指摘なし | 結果と次操作の各状態、3画面幅を確認。 |
| [stories/components/templates/interview/PracticeStartTemplate.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/templates/interview/PracticeStartTemplate.stories.tsx) | 指摘なし | モードと開始の各状態、3画面幅を確認。 |
| [stories/components/templates/PracticeForm.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/components/templates/PracticeForm.stories.tsx) | 指摘なし | 表示専用への変更、評価・失敗・終了Dialog・旧進捗を確認。 |
| [stories/fixtures/index.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/fixtures/index.ts) | 指摘なし | 検証済みUUID・質問・評価・結果・v2 Store fixtureを確認。 |
| [stories/fixtures/refactor.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/fixtures/refactor.ts) | 指摘なし | 管理者一覧の固有ID、編集用不正入力fixture、新規一巡終了fixtureを確認。 |
| [stories/pages/admin/QuestionManagement.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/pages/admin/QuestionManagement.stories.tsx) | 指摘なし | 編集・保存・追加/移動/削除・復旧・再確認・競合・403の操作を確認。F4の古いCache条件は未網羅。 |
| [stories/pages/auth/Login.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/pages/auth/Login.stories.tsx) | 指摘なし | OTP開始・成功遷移・誤コード・メール変更を確認。 |
| [stories/pages/feedback/FeedbackResult.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/pages/feedback/FeedbackResult.stories.tsx) | 指摘なし | 結果取得、次問再確認、古い結果、最終問、新規一巡終了を確認。 |
| [stories/pages/interview/PracticeSession.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/pages/interview/PracticeSession.stories.tsx) | 指摘なし | 旧Templateから移したhooks統合の送信・復旧・評価・終了・遷移を確認。 |
| [stories/pages/interview/PracticeStart.stories.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/pages/interview/PracticeStart.stories.tsx) | 指摘なし | full/category開始、未確定要求、401、カテゴリ消失を確認。F1/F2の利用者切替中の応答は未網羅。 |
| [stories/test-utils/presentation.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/test-utils/presentation.tsx) | 指摘なし | 表示専用HarnessのRHF/FieldArrayと固定view/actionsを確認。 |
| [stories/test-utils/storyEnvironment.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/stories/test-utils/storyEnvironment.tsx) | 指摘なし | Query/Router/認証/Storage/memoryのStory間初期化と購読後処理を確認。 |

### tests（13ファイル）

| ファイル | 結果 | 確認内容 |
|---|---|---|
| [tests/answer.test.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/answer.test.tsx) | 指摘なし | 利用者別キーへの更新、未確定要求優先と下書きの再マウントを確認。 |
| [tests/api.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/api.test.ts) | 不足 F1 | エラー写像・冪等性・Timeout/Abortは確認。401待機中の利用者切替条件がない。 |
| [tests/auth.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/auth.test.ts) | 指摘なし | refresh単一実行、client/sub不一致、logout後のchallenge応答を確認。API応答の利用者切替とは別の試験。 |
| [tests/backend-contract.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/backend-contract.test.ts) | 指摘なし | 共有fixtureと15問の原本一致を確認。 |
| [tests/cognito-adapter.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/cognito-adapter.test.ts) | 指摘なし | SDK Command入力、EMAIL_OTP選択、refresh/revoke、自動Retryなしを確認。SDK自体はstub。 |
| [tests/contracts.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/contracts.test.ts) | 不足 F3 | 書込失敗を検査するが、その後の読取で最新memoryを復旧できるかを検査していない。 |
| [tests/e2e/practice.spec.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/e2e/practice.spec.ts) | コード上の指摘なし | カテゴリ選択・v2 Storeへの変更、回答境界・復旧・画像失敗の期待値を確認。今回E2Eは未実行。 |
| [tests/e2e/question-management.spec.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/e2e/question-management.spec.ts) | コード上の指摘なし | 管理者保存・新規反映・既存質問保持・最終問・USER拒否・幅を確認。今回E2Eは未実行。 |
| [tests/integration/practice.test.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/integration/practice.test.tsx) | 指摘なし | PracticeSessionContentへの移動、送信・復旧・文字数境界を確認。 |
| [tests/mock-migration.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/mock-migration.test.ts) | 不足 F5/F3 | 質問snapshotの移行・原本保全は確認。旧requestsの再送と書込だけが失敗する条件がない。 |
| [tests/question-management.test.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/question-management.test.ts) | 指摘なし | 公開・所有者・版競合・再送・一巡終了のAPI契約を確認。 |
| [tests/refactor.test.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/refactor.test.tsx) | 不足 F2/F4 | 固定要求、競合参照、403、OTP待機、Cache消去、遷移は確認。遅延応答と古いCache復旧がない。 |
| [tests/setup.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/tests/setup.ts) | 指摘なし | 各テスト前のMock認証とDOMの後処理を確認。 |

### 設定・説明（8ファイル）

| ファイル | 結果 | 確認内容 |
|---|---|---|
| [.env.example](C:/Users/user/Documents/ai_interview_mvp_design/frontend/.env.example) | 指摘なし | 認証用の公開識別子の追加を確認。 |
| [.storybook/main.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/.storybook/main.ts) | 指摘なし | StorybookだけのMSW環境定数と既存defineの保持を確認。 |
| [.storybook/preview.tsx](C:/Users/user/Documents/ai_interview_mvp_design/frontend/.storybook/preview.tsx) | 指摘なし | 認証利用者設定後のStorage fixture、Story環境初期化、MSW handler/repositoryの初期化を確認。 |
| [next.config.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/next.config.ts) | 指摘なし | Backendの共有JSONを扱うTurbopack rootとStatic Export設定を確認。今回buildは未実行。 |
| [package.json](C:/Users/user/Documents/ai_interview_mvp_design/frontend/package.json) | 指摘なし | 認証SDKの固定versionと既存scriptsを確認。依存脆弱性監査は対象外。 |
| [package-lock.json](C:/Users/user/Documents/ai_interview_mvp_design/frontend/package-lock.json) | 指摘なし | 追加SDKと固定依存のpackage.json整合を確認。依存脆弱性監査は対象外。 |
| [README.md](C:/Users/user/Documents/ai_interview_mvp_design/frontend/README.md) | 指摘なし | hooks分離、表示Story/統合Story、認証・質問管理の説明とコードの対応を確認。実AWSの証明は含まれない。 |
| [vitest.config.ts](C:/Users/user/Documents/ai_interview_mvp_design/frontend/vitest.config.ts) | 指摘なし | unit/Storybookの分離、共有認証・Storageを使うStoryのfileParallelism=falseを確認。 |
