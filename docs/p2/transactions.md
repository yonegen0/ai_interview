# P2-204・205 TransactionとDurable Acceptance

状態: 設計確定（2026-09-12）。[属性](entity-model.md)、[物理操作](dynamodb-design.md)、
[状態遷移](state-machine.md)を同時に満たす。ここでの「更新」はCAS付きPutによるitem全置換を指す。

## 共通の読取り・条件・障害規則

更新itemは常に `attribute_exists(PK) AND rev = :observedRev AND kind = :expectedKind AND schema_version = :v1`。
新規itemは `attribute_not_exists(PK)`（そのPK/SK組の不在）。
更新しない可変依存itemは同じrev等のConditionCheckを置く。
同一itemへのPutとConditionCheckを重ねない。状態・owner・世代・時刻の業務検証はdataをdecodeして行い、
それを読んだrevが変わらないことをTransactionで確認する。条件式からJSON内部は参照しない。
不変Attemptは事前の強整合読取りで関連を検証。P3では削除/変更しないため通常はConditionCheck不要。
内部処理は複数可変itemをTransactGetしてから分類する。Session参照欠落は正常な「別active」ではない。

各Txの条件不成立は読み直して分類する。POSTは常に冪等記録→Session、
内部処理はE/D→必要なA/Sの順で再確認する。
DB通信・スロットルはStorageUnavailable、予算消費はRetryExhausted。
公開では固定500/INTERNAL_SERVER_ERROR（生例外なし）、Worker/Dispatcherでは配送再試行経路へ返す。
業務409は新鮮な状態によって証明できた場合だけ。ID衝突/破損/schema不一致も500で通知する。

## Transaction仕様票

S/A/E/D/IはSession/Attempt/Evaluation/Dispatch/IdempotencyRecord。
読み取るitemの全dataとrevを使う。表の参照はすべて同じowner。
「正常再実行」はDB障害と別であり、表の結果を返す前にも現在状態を再確認する。

| ID/主体・操作 | 読取り | Put新規/更新 | 条件だけ確認 | 業務前提と成功後 | 競合後・正常再実行 |
|---|---|---|---|---|---|
| T01 API/create | I | S新規、I新規 | なし | 検証済カテゴリsnapshot非空。S番号1/active=null、I元201 | I同hash→元201、異hash→409。不在なら上限内再試行 |
| T02 API/accept・retry | I,S | S更新、A/E/D/I新規（5件） | なし | question一致、S.activeがnull/completed/failed。S.version+1/active processing、A immutable、E pending/not_started、D PENDING世代1、I元202 | I優先。その後processing/質問変化はSESSION_STATE_CONFLICT。部分保存なし |
| T03 API/next | I,S | S更新、I新規 | なし | active completedかつfromAttemptId一致。number+1/active=null/version+1、I元200 | I優先。現在active不一致/未完了なら409 |
| T04 Worker/claim | E,D,A,S | E,D更新 | S.rev | 参照整合、E pending/not_started、D現世代PENDING/QUEUED、deadline未到来。E running/lease_version+1/新実行権/設定、D CLAIMED・send/claim_due除去 | terminal/stale/busy/missing/deadline_due。期限切れrunningもbusyで直接再取得しない |
| T05 Worker/start | E,D | E更新 | D.rev | 現実行権・running/not_started・D CLAIMED現世代・期限内・呼出予算あり。started/call_started_at設定 | 同一生存実行の保存不明のみconfirmed。同じstartedから2回呼ばない。その他lost_lease |
| T06 Worker/finish | E,D,A,S | E,D更新、active一致時S更新 | active非一致時S.rev | 有効実行権、期限内。成功はstartedと検証済Feedback必須。失敗はnot_startedも可。E terminal、D DONE、index除去、S該当status/version更新 | terminal→already_terminal（保存内容を返す）、旧権利→lost_lease。S競合だけなら再読取りし同じ結果保存 |
| T07 Dispatcher/acquire | E,D | D更新 | E.rev | E pending、D PENDING現世代、now>=next_at、送信権なし/期限切れ、deadline内。新送信権45秒、総/世代試行回数+1 | not_due/busy/obsolete/deadline_due。新送信者だけSQSを1回呼ぶ |
| T08 Dispatcher/confirm | E,D | D更新 | E.rev | E pending、D PENDING、現世代と同じ未期限切れ送信権。QUEUED、queued_at=now、claim_due=now+120秒、送信権除去 | CLAIMED/DONE/新世代/旧権利はobsolete。既に同世代QUEUEDなら送信済事実を確認し終了 |
| T09 Dispatcher/fail | E,D | D更新 | E.rev | T08と同じ権利。PENDING維持、next_at=backoff後、送信権除去 | obsoleteなら無変更。応答不明でもSQSをこの実行中に再呼出しない |
| T10 Recovery/queued | E,D | D更新 | E.rev | E pending/not_started、D QUEUED、claim_due到来、deadline内。世代+1/PENDING/next_at=now、世代試行0、queued/claim_due/send除去 | claim済ならunchanged。期限到来ならT13。古い世代を変更しない |
| T11 Recovery/unstarted | E,D,A,S | E,D更新 | S.rev | E running/not_started、lease到来、D CLAIMED、deadline内。E pending・lock/config除去、lease_version保持。D世代+1/PENDING、next_at=now、世代試行0、配送確認除去 | started/terminal/新leaseなら再分類。開始済みをpendingに戻さない |
| T12 Recovery/unknown | E,D,A,S | E,D更新、active一致時S更新 | active非一致時S.rev | running/started、lease到来、deadline内、終端未保存。failed/OUTCOME_UNKNOWN、D DONE、該当S同期 | terminal優先。新観測状態へ再分類。旧Workerの結果を上書きしない |
| T13 Recovery/deadline | E,D,A,S | E,D更新、active一致時S更新 | active非一致時S.rev | 非終端でnow>=deadline。failed/DEADLINE_EXCEEDED、D DONE、該当S同期 | terminalは無操作。期限内へ戻さない |
| T14 Recovery/checkpoint | Cursor | Cursor新規または更新 | なし | 走査cutoff/処理済位置を保存。新規不在/既存rev条件 | 競合は敗者終了。業務処理を巻き戻さない |

Dispatch状態値は大文字4種だけ（条件は文字列の部分一致ではない）。
T04/T11のSは所有関係確認のためでありactive不一致自体は破損ではない。必要な版が変われば再読取りする。
T06/T12/T13でSが別activeまたはnullなら、読んだS.revのConditionCheckにより
「非一致」をTransaction内で担保する。E/Dのみ確定し、S.number/active/versionを変更しない。
所有者/逆参照/存在の破損は全Txを中止しIntegrityError。恣意的な修復・別owner探索はしない。
T10では不変Eを更新せずConditionCheck、T11ではEを更新する。この違いを実装で省略しない。
各Tのindex更新・任意属性の除去は [物理設計](dynamodb-design.md) と [属性辞書](entity-model.md) に従う。

## 冪等性・再試行・時刻

POST順序を固定する:

1. 主体、ID、要求Schema、Idempotency-Keyを検証する。
2. owner＋keyを強整合取得。fingerprint_versionとhash一致なら元Status/bodyを返す。
3. hash不一致は409。未登録だけ現在業務状態を検証する。
4. 生成ID、受付日時、元応答を要求内で固定しTxを作成する。
5. Tx成功またはIの同hash保存確認で成功を返す。
6. 条件失敗・通信不明はIを再確認し、見つからない場合だけ状態再判定または予算内再送。

合計書込み送信は1要求最大3回（初回含む）、処理全体5秒のmonotonic予算。
SDKはtotal_max_attempts=1で内部再試行を無効化する。
DB connect/read timeoutは各0.2秒、各送信前に残予算0.4秒以上があることを確認。
再試行待ちはfull jitter、上限100ms/200ms。予算内に読取り確認ができなくても500で受付不明とする。
ローカル/実機の遅延試験でこの設定の可用性を確認し、成功率のために無制限retryへ変えない。
OS/DNS停止や実行基盤の停止を含む厳密な応答5秒SLAではなく、アプリの再試行予算である。

同じ送信内容の通信再送はClientRequestToken（UUID）、全payload、時刻、IDを固定する。
状態再読取りで条件/時刻/結果が変わった場合は新しい候補Txと新tokenにする。
元Txが成功不明でも、I不在条件やE/D.revで複数候補の二重適用を防止する。
ClientRequestTokenの10分保証は永続冪等性の代わりにしない。
[AWS Transaction再送規則](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)

時間依存の内部Txは毎回送信前に現在時計で権利/deadline/予算を再評価する。
期限後は古いnowのTxを再送せず強整合確認のみ。期限前でも条件用nowを更新する再評価は新token。
未決の元Txと新候補の両方が同revを更新することはできない。
DynamoDBはサーバー現在時刻と比較する式を持たない前提で、revによるfencingと送信前チェックを組み合わせる。
送信中に期限を跨いだ書込みは、先にRecoveryがrevを更新していれば失敗、書込みが先にcommitすれば保存終端を優先する。
「期限到来と同時刻にDBが自動失効する」とは保証しない。
開始記録が遅れて返った場合は再度期限と残予算を確認し、Providerを呼ばない。

## 202と結果不明の意味

202はS/A/E/D/Iの5件commit確認を意味する。SQS SendMessage成功は必要条件ではない。
Iは同一Txの成功証拠なので毎回5件を別々に読んで証明する必要はない。
I不在の瞬間だけで「未受付」を断定しない。通信不明・予算終了は固定500とし、
Frontendの保存済みキーと本文による手動再確認へ渡す。新キーを自動生成しない。
HTTP 502/504やFrontend TIMEOUTも受付取り消しを意味しない。

開始記録応答消失: 同一生存execution_idがstarted・同lease・現世代・期限を再確認できた時だけ初回呼出に進む。
プロセス内にも「呼出に進んだ」フラグを持ち、再確認ループから再び呼ばない。
確認不能なら呼ばず停止し、後でRecoveryがstartedを結果不明として扱う。

finish応答消失: E/Dを整合読取りしてterminalなら既存結果を採用しack。
結果がメモリにあって未保存かつ有効leaseなら同じFeedback/createdAtの保存のみ再試行。
結果を失ったプロセスを再起動してProviderを再呼出しない。

決定理由: 永続成功記録と業務更新の同時commitで元応答を再現する。
予約item/処理中冪等状態・API直接SQS成功を202条件にする案・業務409への一括変換を見送る。
確認R01〜R17。P3-305/306/307でTx拒否時の部分保存なしとcommit応答消失を試験する。
