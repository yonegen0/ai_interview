# STAR Ver.1.4 実装設計

既存評価への入力は最終表示から正式送信された本文だけである。STAR起動・生成・編集・保存・反映でAttempt/Evaluationを作成しない。V2/V1の採点、回答Body、初回Evaluation ID、深掘り累積を維持する。

## API

全変更要求はUUID Idempotency-Key必須。保存系応答は本文を含まないreceipt。ownerは認証済みJWT subだけを用い、Bodyにownerは受け付けない。新規POST、更新PUT、破棄POSTを分ける。

|Method / Path|入力/出力の要点|
|---|---|
|GET `/star-assist/options`|固定10カテゴリ、20/600上限|
|GET/PUT `/star-assist/preferences`|category/details各expectedGenerationとexpectedVersion、独立期限|
|POST `/sessions/{id}/answer-contexts`|questionId, operationKind, 操作起点Attempt/Evaluation|
|GET `/answer-contexts/{id}/drafts`|有効な通常/STAR下書き、期限切れはnull|
|POST `/answer-contexts/{id}/answer-drafts`|answer, nullable applicationId|
|PUT `/answer-drafts/{id}`|expectedVersion + answer + nullable applicationId|
|POST `/answer-drafts/{id}/discard`|expectedVersion|
|POST `/answer-contexts/{id}/star-drafts`|notes S/T/A/R、カテゴリ、industry/company、3案、選択、generationId|
|PUT `/star-drafts/{id}`|expectedVersion + STAR入力|
|POST `/star-drafts/{id}/discard`|expectedVersion|
|POST `/star-assist/generations`|starDraftId, expectedVersion → 202 generationId|
|GET `/star-assist/generations/{id}`|状態、固定期限、nullable結果、Fake費用情報|
|GET `/star-assist/quota`|JST月、user/global予約/消費/残枠|
|POST `/star-drafts/{id}/applications`|STAR版、案ID、通常下書きID/版 → applicationIdとreceipt|
|GET `/star-assist/requests/{key}`|元Method/Path/hash/receipt、本人だけ|

新APIの正本はPydantic `star_assist/models.py`、Zod `schemas/star.ts`、共有 `contracts/star-v14-fixtures.json`。400 Unicodeコードポイントを再検証し、原文を正規化・切詰めしない。未完成の通常下書きは16000コードポイントまで保持し、正式送信時には既存の400制限を適用する。メモ各2000、業界100、企業名200。

エラーは400入力不正、401未認証、404未知/別owner、409版・世代・終了・起点・同キー衝突、413保存サイズ、429枠不足、500固定内部エラー。機密本文を例外・ログへ出力しない。

## 物理キー・期限

本人PK=`USER#sub`。SKは`TARGET_CATEGORY#CURRENT`, `TARGET_DETAILS#CURRENT`, `ANSWER_CONTEXT#uuid`, `ANSWER_DRAFT#uuid`, `STAR_DRAFT#uuid`, `STAR_GENERATION#uuid`, `STAR_REQUEST#key`, `STAR_APPLICATION#uuid`, `ANSWER_ASSIST#evaluationId`, `STAR_QUOTA#YYYY-MM`。全体quotaは`SYSTEM#STAR_QUOTA` / `MONTH#YYYY-MM`。Recovery持回りは`SYSTEM#RECOVERY` / `ROTATION`。

|対象|有効期限|更新契機|
|---|---|---|
|category|14×24時間|明示選択の新要求成功、同カテゴリ再選択も更新|
|industry/company|14×24時間|内容変更保存成功|
|STAR下書き|7×24時間|内容変更保存成功|
|通常下書き|14×24時間|内容変更保存成功|
|Generation本文|終端から7×24時間|終端確定時固定|
|application|通常下書き期限に追従|通常下書き保存|

トップレベル`expiresAt`はNumber epoch秒。UTCサーバー時計で期限後の取得・更新・新規反映を拒否し、GETでは延長しない。完了/破棄下書きは本文を除去する。StarRequestにはPayloadを保存せずhashと最小receiptを保全する。

TTLの物理削除時期は非同期である。API失効と物理削除を区別し、今回の保証はAPI拒否。[AWS TTL仕様](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)

## CAS・正式送信・復旧

文脈IDはowner、Session質問スナップショットhash、質問番号/ID、操作種別と起点IDからUUIDv5で固定する。深掘りはserver pending questionを使用し、初回/再挑戦とは別文脈。retry_evaluationは入力文脈を作らない。

設定はimmutable保存世代ID＋version、下書きはID＋version＋文脈の現在参照でCASする。TTL後再作成で新IDを用い、PUTで再作成しない。冪等成功応答は現在の期限/状態判定より先に再現する。他APIのowner/key衝突も原子的に確認する。

既存正式受付transactionへ、文脈完了、通常/STAR下書きscrub、任意application使用記録、未開始生成の取消/予約返却を追加する。最終本文はBodyを正本とし、自動保存成功を必須にしない。通常下書きだけの破棄はSTARを閉じない。

結果不明時はscoped storageの同key/元Payload/hash/期待版/編集世代を保持し、本人request GET→receipt確認→最新draft GETで照合する。404でも新keyを発行せず同要求を手動再送する。409でversionを差し替えて自動再送しない。

Frontendは1秒debounceで同下書きを直列保存し、追加編集を最新内容にまとめる。復元優先はpending→server draft→retry前回初回Feedback.answer→空欄。新version3ローカルcacheがserver draftに結び付く場合、server GETの現存確認まで復元を待つ。旧v1/v2 pendingはBodyを変換しない。

## 生成・quota・配送

生成受付は本人/全体予約、Generation、StarRequest、Dispatch、context.activeGenerationIdを1transactionで確定し、同文脈の別key同時生成を409にする。JST月はCommitWindowで受付境界を検査。旧月予約の取消は旧月へ返す。予約＋消費で20/600を判定。[AWS transaction仕様](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

`QUEUED → PREPARED → STARTED → SUCCEEDED / NEEDS_INFORMATION / FAILED_AFTER_START / OUTCOME_UNKNOWN`。
開始前は`CANCELLED / FAILED_BEFORE_START`で一度だけ返却。STARTEDを永続確認して予約を消費へ変更した後、Providerを一度だけ呼ぶ。開始/結果保存の応答不明は同lease/同結果の保存確認だけを再試行する。確認不能・lease失効では再Provider呼出しも返却も行わない。終了contextへ結果を書き戻さない。

開発用FakeProviderは本人の入力事実を順序変更してA結論/B行動/C会話の3案を返す。本番Workerは明示選択済みのBedrockまたはOpenAI通信境界をSTAR専用アダプターへ渡し、暗黙のFake選択や自動fallbackを行わない。[実AI接続・制約・検証方法](STAR_V14_LIVE_ADAPTER.md)を参照。公開StarResult契約と編集・履歴・Coaching V2経路は維持する。

Dispatch.job_kind=`star`だけが`StarGenerationRequested`になる。未指定は旧Evaluationとし保存bytesと旧イベントを維持する。StreamsはDispatch NewImageだけ、REMOVE/下書きを無視。Worker/SQSは保存job種別とイベントを照合する。WorkIndexは従来3領域＋`WORK#STAR_RUNNING`、Recoveryは永続開始位置を持ち回り、各巡回で各領域を最大1ページずつ処理する。cursor競合で停止し途中位置を保持する。timeout40秒、deadline15分、MaximumConcurrency2を維持する。

## Mock V4

共有IndexedDB `pocket:mock:v4` / state / currentを正本にする。全MSW handlerがreadwrite transaction内の純粋処理を使用し、delay/通信/Fake生成はtransaction外。応答はcommit確認後。BroadcastChannelは通知だけ。IndexedDB障害/破損では停止し、旧版へfallbackしない。

V4未作成時だけ検証済みV1/V2/V3をコピーし、sourceHash markerとstateを同時保存する。元sessionStorageキーを保持する。V4作成後に異なる古いデータがあれば未統合表示し再投入・mergeしない。
