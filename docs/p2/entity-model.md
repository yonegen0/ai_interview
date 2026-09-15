# P2-202 Entity・内部契約

状態: 設計確定（2026-09-12）。実装・実機試験の完了ではない。
決定と机上確認の対応は [確認記録](P2_VERIFICATION.md)、遷移は [状態表](state-machine.md)。
[依存方針](../DEVELOPMENT_DEPENDENCY_POLICY.md)を適用する。

## 現実装との差

| 分類 | 確認した事実 |
|---|---|
| 実装済み | Memoryのcopy-on-write＋RLock、3 POST成功応答再現、3 GET、カテゴリ内の質問巡回、明示Worker |
| 未実装 | 受付時Dispatch保存、永続化、分散排他、開始記録、配送、回復 |
| 先行変更 | internal.pyの時刻・lease・Dispatch型。Memory/Worker未接続。初期値0や空文字を設計根拠にしない |
| 設計 | 以下の属性・内部Interface・結果分類。P3でMemoryから接続する |
| 公開契約 | [6 API契約](../FRONTEND_API_CONTRACT.md)と既存Zodを維持。内部状態を公開しない |

現在のApplication fingerprintは検証済み要求の正規化JSONそのもの。P3では同じ文字列のSHA-256を保存する。
Provider開始済み・期限切れ等を現Memoryが制御済みとは扱わない。

## 属性辞書の共通規則

論理名はsnake_caseに統一。イベントのdispatchVersionだけはDispatch.generationへ写像する。
必須=常に存在、任意=未設定時は省略（空文字・0を未設定の代用にしない）。
時刻型TはUTC epochミリ秒の非負整数。実行時計はUTC、時間予算はmonotonic時計を使用する。
公開日時はUTC ISO 8601のZ形式。保存期限ではない。各表の「初期/更新主体」が作成・変更権限を定める。
公開欄の「ID」は必要な既存応答にのみ出力。「間接」は関連Feedback/Questionへ写像。「なし」は非公開。
機密欄: 識別=個人に関連する識別子、本文=個人回答・生成文章、なし=業務設定。識別子も生ログ禁止。

全5 Entity共通属性（各Entityに含む）:

| 属性・意味 | 型/必須 | 初期値 | 可変性/更新主体 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|---|
| owner: 所有者sub | string/必須 | 認証済みsub | 不変/API | 全参照先と一致 | なし | 識別 |
| created_at: 作成時刻 | T/必須 | 当該受付のnow | 不変/API | Evaluation/Attempt/Dispatch/回答冪等記録で同一 | なし | なし |

### Session

| 属性・意味 | 型/必須 | 初期値 | 可変性/更新主体 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|---|
| id | UUID/必須 | 生成ID | 不変/API | owner内一意 | ID | 識別 |
| questions: 順序付き完全snapshot | Question[]/必須 | 指定カテゴリの全質問 | 不変/API | 非空。各Questionはid/category/difficulty/question。作成後Bankを参照しない | 間接 | なし |
| number: 累計質問番号 | 正整数/必須 | 1 | 次問APIのみ+1 | 現在質問=questions[(number-1)%件数] | questionNumber | なし |
| active | ActiveAttemptまたはnull/必須 | null | 回答API・次問API・終端Worker/Recovery | attemptId/evaluationId/statusは対応Evaluationと一致 | activeAttempt | 識別 |
| version: 業務更新番号 | 非負整数/必須 | 0 | 回答・次問・active終端更新で+1 | GETでは不変。物理revとは別 | なし | なし |
| updated_at | T/必須 | created_at | Session更新主体 | 作成時以上。遅延時計ではmax(旧値,now) | なし | なし |

Sessionに終了状態はない。再挑戦はnumberを変えずactiveだけ新しくする。

### Attempt（全属性が受付後immutable）

| 属性・意味 | 型/必須 | 初期値/作成主体 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|
| id | UUID/必須 | 生成/API | owner内一意 | ID | 識別 |
| session_id | UUID/必須 | 対象Session/API | owner一致 | 間接 | 識別 |
| evaluation_id | UUID/必須 | 同時生成/API | Evaluation.attempt_idとの双方向一致 | ID | 識別 |
| question | Question/必須 | Sessionの現在snapshot/API | 完全複製 | Feedback.question | なし |
| question_number | 正整数/必須 | Session.number/API | 受付時番号 | Feedback.questionNumber | なし |
| answer | string/必須 | 検証済み元本文/API | UTF-16で1〜500、JS空白のみ不可、無加工 | Feedback.answer | 本文 |

### Evaluation

| 属性・意味 | 型/必須 | 初期値 | 可変性/更新主体 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|---|
| id | UUID/必須 | 生成ID | 不変/API | Attempt.evaluation_id、Dispatch.idと一致 | ID | 識別 |
| attempt_id | UUID/必須 | 同時生成ID | 不変/API | Attempt.idと一致 | ID | 識別 |
| deadline_at | T/必須 | created_at+900000 | 不変/API | Dispatchと一致 | なし | なし |
| status | processing/completed/failed/必須 | processing | 終端Worker/Recoveryのみ変更 | 状態表の有効組合せのみ | status | なし |
| worker_state | pending/running/terminal/必須 | pending | claim・finish・Recovery | terminal不可逆 | なし | なし |
| call_phase | not_started/started/必須 | not_started | Worker開始記録だけstartedへ | startedを戻さない | なし | なし |
| lease_version | 非負整数/必須 | 0 | claimで+1 | 回復後も減らさない | なし | なし |
| lock_owner | UUID/任意 | 省略 | claimでexecutionId設定、未開始再投入で除去 | runningには必須。terminalは最後の権利を監査用保持 | なし | 識別 |
| lock_expires_at | T/任意 | 省略 | claimでnow+90000、再投入で除去 | running必須、更新/延長なし | なし | なし |
| call_started_at | T/任意 | 省略 | 開始記録時に一度設定 | startedのとき必須 | なし | なし |
| execution_config | Map/任意 | 省略 | claim時に設定、未開始再投入で除去 | runningでは必須。started後不変 | なし | なし |
| feedback | Feedback/任意 | 省略 | Worker成功確定で設定 | completedだけ必須。既存公開Schema検証済み、score整数、exampleAnswerのnull禁止 | Feedback GET | 本文 |
| error | ErrorBody/任意 | 省略 | Worker/Recovery失敗確定で設定 | failedだけ必須。下記固定値 | 評価GET.error | なし |
| failure_reason | enum/任意 | 省略 | 失敗確定主体 | failedだけ必須 | なし | なし |
| finished_at | T/任意 | 省略 | 終端化時に一度設定 | terminalだけ必須 | なし | なし |

execution_configの全項目は必須・claim時Worker設定から複製:
provider_id:string、model_id:string、prompt_version:string、result_schema_version:integer=1、
provider_timeout_ms:integer=40000。P3はprovider_id/model_idともfake。
秘密値、Prompt本文を入れない。claim直後に実行可能な版か検証し、不一致は開始前の固定失敗。
未開始回復後の新claimでは最新デプロイの設定を使えるが、開始後は変更しない。
実Providerの具体モデル/認証/SDK選定はP5 Gateであり、P3 Fakeの未決事項ではない。

failure_reasonは PREPARATION_FAILED / PROVIDER_FAILED / PROVIDER_TIMEOUT /
INVALID_RESULT / RESULT_TOO_LARGE / OUTCOME_UNKNOWN / DEADLINE_EXCEEDED。
公開errorは常に
`{"code":"EVALUATION_FAILED","message":"Evaluation could not be completed."}`。
DB障害・参照破損をProvider失敗へ偽装しない。DBに終端を保存できない間はprocessing。

### Dispatch

| 属性・意味 | 型/必須 | 初期値 | 可変性/更新主体 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|---|
| id | UUID/必須 | Evaluation.id | 不変/API | 1対1 | なし | 識別 |
| deadline_at | T/必須 | Evaluation.deadline_at | 不変/API | 常に一致 | なし | なし |
| status | PENDING/QUEUED/CLAIMED/DONE/必須 | PENDING | Dispatcher/Worker/Recovery | 状態表参照 | なし | なし |
| generation: 配送世代 | 正整数/必須 | 1 | Recovery再投入で+1 | 古いイベント無効化用。通常送信再試行では不変 | なし | なし |
| delivery_attempts: 総送信権取得回数 | 非負整数/必須 | 0 | acquire_deliveryで+1 | 世代変更でも保持。実SQS成功数ではない | なし | なし |
| generation_attempts: 現世代送信権取得回数 | 非負整数/必須 | 0 | acquireで+1、世代更新で0 | backoff計算用 | なし | なし |
| next_at | T/必須 | created_at | Dispatcher失敗・Recovery再投入 | PENDING配送予定。その他状態では参考値 | なし | なし |
| send_owner | UUID/任意 | 省略 | 送信権取得で設定、確認/失敗/claim/回復で除去 | PENDINGだけ保持可 | なし | 識別 |
| send_expires_at | T/任意 | 省略 | 取得でnow+45000、上記と同時除去 | send_ownerと同時存在 | なし | なし |
| queued_at | T/任意 | 省略 | 送信確認で設定、世代更新で除去 | 現世代の確認時刻。Worker先着では省略可 | なし | なし |
| claim_due_at | T/任意 | 省略 | 送信確認でqueued_at+120000、claim/回復/終端で除去 | QUEUEDだけ必須 | なし | なし |

DONEで配送を再開しない。DLQはSQS側の事実でありDEAD_LETTERED属性を追加しない。

### IdempotencyRecord（旧コード名IdempotentReply。全属性不変、作成主体API）

| 属性・意味 | 型/必須 | 初期値 | 整合条件 | 公開 | 機密 |
|---|---|---|---|---|---|
| key | UUID/必須 | 要求Header | owner＋key単位、Pathをキーへ足さない | なし | 識別 |
| fingerprint_version | 正整数/必須 | 1 | 読取り側はv1をサポートし続ける | なし | なし |
| request_hash | string/必須 | SHA-256小文字hex | v1=現ApplicationのJSON（Method/Path/検証済みPayload）をASCIIとしてhash。本文加工なし | なし | 本文由来 |
| reply | Map/必須 | 元成功応答 | status:整数201/202/200、body:既存応答object。最新状態で更新しない | 同一要求POST | 識別/質問 |

bodyの全属性は既存公開Schemaに従う。成功記録だけを保存し、予約・処理中・エラー記録は作らない。
同一キー異Path/異本文は409、別ownerの同キーは独立。既存保存version・未確定要求移行は変更しない。

## 参照と内部Interface

全関連owner一致、Attempt↔EvaluationとEvaluation↔Dispatchは1対1。
再配送で新Attempt/Evaluationを作らず、再挑戦だけ新規作成。過去FeedbackはSession.activeに依存せず保持。
関連欠落・ID逆参照不一致はIntegrityError、未知保存schemaはStorageFormatError。
対象EvaluationもDispatchもないイベントはmissing（監視してack）、片方だけ欠落はIntegrityError。
PKから取り出したownerとdata.ownerが違う場合もIntegrityError。Provider呼出禁止。

| 操作 | 必須入力 | 成功・正常競合の結果 |
|---|---|---|
| claim | owner, evaluation_id, generation, 新execution_id, execution_config, now | acquired(LeaseClaim) / busy / terminal / stale / missing / deadline_due |
| mark_call_started | LeaseClaim, now | applied / confirmed_same_execution / lost_lease |
| finish | LeaseClaim, 検証済み結果または固定失敗, now | applied / already_terminal / lost_lease |
| acquire_delivery | owner, evaluation_id, generation, 新sender_id, now | acquired(DeliveryClaim) / not_due / busy / obsolete / deadline_due |
| confirm_delivery | DeliveryClaim, 送信成功事実, now | applied / obsolete |
| fail_delivery | DeliveryClaim, 安全な失敗分類, next_at, now | applied / obsolete |
| recover | owner, evaluation_id, 観測rev/generation/lease_version, now | requeued / failed / unchanged |
| due_candidates | partition, cutoff, cursor, limit | candidates, continuation（業務状態変更なし） |

LeaseClaimはowner/evaluation_id/attempt snapshot/generation/execution_id/lease_version/
lock_expires_at/deadline_at/execution_configを返す。
DeliveryClaimはowner/evaluation_id/generation/sender_id/send_expires_at。
DB通信失敗はStorageUnavailable、競合再試行予算消費はRetryExhaustedとして別経路で通知する。
正常分類へ吸収しない。already_terminalは「今回の結果を保存した」の意味ではなく既存終端を返す。
markのconfirmedは現在生存中の同一実行が自分の保存応答を失った場合のみ。
プロセス再起動は必ず新execution_idであり、保存済みstartedを再呼出権にしない。

## 決定理由・引継ぎ

snapshotとimmutable Attemptを採用し、Bank再参照・再配送で新評価を作る案を見送った。
公開/内部状態の分離で現Frontendを保つ。処理権・世代・送信回数を分け、旧Workerと旧送信確認を排除する。
物理revやGSIはdomainへ露出させず [物理設計](dynamodb-design.md) で追加する。
確認: R01〜R19（確認記録）。P3-301で現モデル名とのMapperを接続し、初期値0の意味を引き継がない。
