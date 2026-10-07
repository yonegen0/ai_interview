# frontend/src 未コミット変更レビュー

実施日: 2026-10-07（JST）。対象は変更済み20ファイルと未追跡6ファイル、計26ファイル。
HEADとの差分、新規ファイルの全文、呼出元、API契約、関連テストを読み合わせた。
レビュー時点では製品ソースを変更していない。その後、ユーザー指示によりF1を修正した（末尾参照）。

## 指摘 F1 — P2: 現在の練習へ戻ると深掘り回答の下書きが消える

状態: 修正済み。以下はレビュー時点の再現内容。

対象: `frontend/src/hooks/useAnswerOperation.ts:102–104`。

深掘り質問が表示されている結果画面で回答を下書きし、「現在の練習へ戻る」を開くと、
まだ送信していない下書きが削除される。

1. `CoachingResponse` は `operation.kind=coaching_answer` と元Evaluation IDを渡し、
   `pocket:answer:<sessionId>` に深掘り回答のdraftを保存する。
2. 結果画面の「現在の練習へ戻る」は同じSessionの通常の練習URLを開く。
3. 通常の練習ではoperationが未指定なのでcontextが異なり、このdraftを読取り対象にしない。
   ただし、保存キーは同じSession単位のキーのままである。
4. 直前のEvaluationはcompletedなので、完了Effectが無条件に`removeSaved(storageKey)`を呼ぶ。
5. 結果画面へ戻った深掘りフォームではdraftを復元できず、空になる。

`completed`はこの場合、直前の評価の完了であり、次の深掘り回答を送信したことを意味しない。
保存レコードのcontext／対象Evaluationを照合して今回の操作が所有するレコードだけを削除するか、
操作単位に保存キーを分け、awaiting_answerの下書きを保持する必要がある。

一時的なVitestで、awaiting_answerのSessionと深掘りdraftを用意し、
通常の練習と同じ`useAnswerOperation(session, null)`をマウントした。
completed応答の後に保存レコードがnullになることを確認した。再現テスト1件成功。
ブラウザでのクリック経路は呼出元のコードを読み合わせて確認した。今回ブラウザテストは実行していない。
一時テストと一時設定ファイルは検証後に削除した。

## ファイル別レビュー

「追加指摘なし」は今回確認した差分についての判断であり、全操作の無欠陥を保証するものではない。
F1を複数ファイルに重複した不具合として数えていない。

| No. | ファイル（frontend/src/からの相対パス） | 確認内容・結果 |
| --- | --- | --- |
| 1 | features/admin/components/molecules/QuestionEditorCard.tsx | 200コードポイントのカウンター、バリデーションメッセージ、既存長文の表示。追加指摘なし。 |
| 2 | features/admin/hooks/useQuestionBankEditor.ts | baselineに応じたresolver、フォームと質問配列の操作。追加指摘なし。 |
| 3 | features/admin/hooks/useQuestionManagement.ts | baselineの受渡し、新規保存の制限、pendingの元Payload再確認。追加指摘なし。 |
| 4 | features/feedback/components/organisms/CoachingResponse.tsx（新規） | 現在のawaiting_answerに限った入力、Evaluationごとのフォーム、送信後の待機URL。F1の深掘りdraft保存側。独立した追加指摘なし。 |
| 5 | features/feedback/components/organisms/FeedbackCard.tsx | V1/V2表示の分岐、30点集計、初回回答・履歴・改善回答の表示。追加指摘なし。 |
| 6 | features/feedback/components/pages/FeedbackResult.tsx | AttemptだけでなくEvaluationも含むContainer key。追加指摘なし。 |
| 7 | features/feedback/components/templates/FeedbackResultTemplate.tsx | coaching結果への入力フォームの組込み。追加指摘なし。 |
| 8 | features/feedback/hooks/useFeedbackNavigation.ts | 現在の完成済みV2に限定した再挑戦・次問、元EvaluationのURL、最新Session取得。F1の通常練習URLへの入口。独立した追加指摘なし。 |
| 9 | features/feedback/hooks/useFeedbackResult.ts | Evaluation付きquery key、URL検証、過去／最新結果の取得。追加指摘なし。 |
| 10 | features/interview/components/molecules/AnswerField.tsx | 新規V2の400文字上限・推奨文字数表示。追加指摘なし。 |
| 11 | features/interview/components/templates/PracticeForm.tsx | V2 failedの履歴表示、評価だけの再試行、再試行拒否のエラー表示。追加指摘なし。 |
| 12 | features/interview/hooks/useAnswer.ts | 共通回答フックへの互換export。処理本体はNo.17、F1参照。 |
| 13 | features/interview/hooks/useEvaluation.ts | 共通ポーリングへの互換export、型export。追加指摘なし。 |
| 14 | features/interview/hooks/usePracticeController.ts | 受付後の待機URL、完了後のEvaluation付き結果URL、コードポイント計測。F1で通常練習の回答フックを呼ぶ経路。独立した追加指摘なし。 |
| 15 | features/interview/hooks/usePracticeSession.ts | 再挑戦・待機の元Evaluation検証、古い起点の案内、フォームの再マウントkey。追加指摘なし。 |
| 16 | features/interview/model/machine.ts | 共通Reducerへの互換export。追加指摘なし。 |
| 17 | hooks/useAnswerOperation.ts（新規） | 固定キー／Payload、V1 pending復旧、V2送信・評価再試行、利用者切替防御。**F1: 別contextの深掘りdraftを完了Effectで削除する。** |
| 18 | hooks/useEvaluation.ts（新規） | 移動前との差分、評価ID変更、terminal停止、可視性・通信状態・時間による停止。追加指摘なし。 |
| 19 | lib/answerMachine.ts（新規） | 送信・不確定・評価・失敗・再試行拒否の状態遷移。追加指摘なし。 |
| 20 | lib/api/feedback.ts | optional Evaluation IDの検証とFeedback URLへの付加。追加指摘なし。 |
| 21 | lib/api/schemas/index.ts | kind／feedbackVersionによる厳密分岐、V1互換、Unicode制限、baseline長文保全、進捗・履歴・点数の整合性。追加指摘なし。 |
| 22 | lib/storage/recovery.ts | 回答保存版1／2の分岐、V1元要求のSchema、Mockの破損データ保持。追加指摘なし。 |
| 23 | lib/textLimits.ts（新規） | コードポイント／旧UTF-16計測、初回回答の減点、合計とrank閾値。追加指摘なし。 |
| 24 | mocks/coaching.ts（新規） | 4種の受付、履歴の累積、評価再試行の入力固定、過去評価による現在進行の巻戻し防止。追加指摘なし。 |
| 25 | mocks/handlers/index.ts | V2分岐、owner確認、元要求の再現、Evaluation別Feedback、次問の完成条件。追加指摘なし。 |
| 26 | mocks/store/index.ts | v1/v2→v3移行、Evaluation／進行の参照整合、旧キー保持、破損v3へのフォールバック防止。追加指摘なし。 |

## 実行結果

- `npm run typecheck`: 成功。
- `npm run lint`: 成功。
- `npm run test:unit`: 16ファイル、259件成功。
- F1の一時再現テスト: 1件成功（不具合の発生を確認するテスト）。

最初の単体テスト起動はサンドボックスの子プロセス制限で`spawn EPERM`となった。
同じローカルテストを承認済みの権限で再実行し、上記の成功結果を得た。
Storybook・Playwright・ビルド・AWS検証は今回実行していない。

## F1の修正と検証

ユーザーの修正指示により、`useAnswerOperation`に保存レコードの所有確認を追加した。
同じquestionIdのレコードについて、pendingは要求キーを照合し、draftはcontextを照合する。
版1の既存contextにも対応する。評価完了・失敗、送信受付・確定拒否、明示終了の削除を
この確認処理に統一し、pending参照をクリアする前に削除対象を照合する。

`frontend/tests/answer-coaching.test.tsx`へ回帰テスト6件を追加した。
深掘りdraftの入力→通常練習→通常練習の終了処理→深掘りフォーム再マウントで
元のdraftを復元できることを、評価キャッシュあり／なしの両方で確認する。
また、今回の操作に属する版1／2のdraftは評価完了／失敗後に削除されることを確認する。

修正後の結果: `npm run typecheck`、`npm run lint`成功。
`npm run test:unit`は16ファイル、**265件成功**。
修正後もStorybook・Playwright・ビルド・AWS検証は実行していない。
