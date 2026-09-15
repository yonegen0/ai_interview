# ADR-004: 永続受付・独立Dispatch・処理権・回復

状態: 採用（P2-206〜209設計確定、2026-09-12）。P3は2026-09-13にレビュー修正とPython検証完了、P4 AWS構築・実DB検証は未実施。
[P3実装・Python試験記録](P3_VERIFICATION.md)を参照。以下の設計・数値は維持する。
[依存方針](DEVELOPMENT_DEPENDENCY_POLICY.md)に従い、選定と構築の許可を分ける。
P1の明示Workerは維持し、P3で以下の内部契約へ接続する。

## P2-206 方式比較と決定

| 案 | 通常遅延 | 保存後停止 | 配送retry/監視 | 構成・保守 |
|---|---|---|---|---|
| API直接SQS送信のみ | 小 | DB成功と送信の穴が残る | API停止後の回収なし | 最小だが受付保証不足 |
| 独立Dispatch＋定期Dispatcher | 最大1周期程度 | DBから回収可能 | due Queryで管理 | Streams不要で軽い |
| 独立Dispatch＋Streams＋定期Recovery | 通常はStreams起点 | Streams停止でもDBから回収 | 配送/実行を別管理 | Lambda起動経路・監視が増える |

3案目を採用。受付5件のcommitと配送を分離し、通常時の待ち時間を抑えつつ起動漏れを回復する。
FIFO/Pipes/Step Functions/shardは初期追加しない。Queue重複抑止に外部呼出のexactly-onceを委ねない。
SQS Standardの重複/順不同をRepositoryで吸収する。P3はPublisher fake、実配送はP4で検証する。

AWSの責務: API Lambda=6 Route、Dispatcher Lambda=Streams配送とScheduler Recovery、
Worker Lambda=SQSから評価実行。業務上のpractice/evaluation/admin分類と配備数は別であり、Admin Lambdaを先回り作成しない。

### Streams adapter

TableはNEW_AND_OLD_IMAGES。event source filterは新画像のkind=Dispatchに限定し、
HandlerでINSERT、またはMODIFYで「旧statusがPENDING以外→PENDING」「generationが変わってPENDING」を選ぶ。
dataはJSON文字列なのでdecodeして新旧を比較する。JSON内部比較をAWS filterで実現できると仮定しない。
PENDINGのsend_owner/next_at/revだけの変更、QUEUED/CLAIMED/DONE、他Entity、REMOVEは配送契機から除外する。
これらのDispatch更新でLambda自体が呼ばれる場合はあるが、Handlerは追加書込み/送信をせず終了する。
Streamsへの自己更新で無限送信を起こさない。将来予定のPENDINGはその場で権利取得せずRecoveryに任せる。
[AWS DynamoDB event filtering](https://docs.aws.amazon.com/lambda/latest/dg/with-ddb-filtering.html)

Stream画像を実行状態の正本とせずbase tableを再読取りする。
Stream内の複数item/順序でTransaction完了を推測しない。
Stream失敗は部分batch失敗を返す。MaximumRetryAttempts=3、MaximumRecordAgeInSeconds=3600、
BisectBatchOnFunctionError=true、ReportBatchItemFailuresを採用。通常batch=100、window=0。
失敗宛先はWorker DLQと別のSQS（Stream failure queue、保持14日）。Recoveryが業務再配送を担う。
破棄通知は元DBへの再照合の契機であり、完全payloadの保管/再生を前提にしない。
[AWS Streams失敗処理](https://docs.aws.amazon.com/lambda/latest/dg/services-dynamodb-errors.html)

### 内部イベントv1

```json
{
  "eventVersion": 1,
  "type": "EvaluationRequested",
  "ownerSub": "synthetic-user",
  "evaluationId": "20000000-0000-4000-8000-000000000001",
  "dispatchVersion": 1
}
```

厳密なobject、上記5項目のみ。version/世代はbool不可の整数、世代>=1、
ownerSubは非空、evaluationIdは既存UUID検証。本文・質問・Prompt・JWT・Secretなし。
unknown version/type/余分な属性/不正型はProvider未呼出、batch失敗→DLQ。イベント全体をログしない。
Scheduler入力は `{"eventVersion":1,"type":"RecoveryTick"}`、Lambdaからの残実行時間と時計を別に渡す。
SQS/Stream/Schedulerのadapterは起動元形式と設定済みARNを照合する。公開HTTP入力を内部イベントとして扱わない。

## P2-207 Worker処理権・外部呼出

1. invocationごとに新execution_idを生成する（SQS messageIdを使い回さない）。
2. owner・関連・配送世代を整合読取り。現PENDING/QUEUED＋pendingだけclaim可能。
3. E.lease_versionを+1、90秒leaseとexecution_configを保存、DはCLAIMEDへ。
4. Prompt準備・設定版・入力を確認。Provider最大40秒＋保存5秒＋余裕5秒を含む50秒以上が
   Lambda残時間、lease残時間、deadline残時間の全てで必要。
5. 残時間不足ならProviderを呼ばない。deadline到来はRecovery、他の不足は有効権利でPREPARATION_FAILEDとして終端化する。
   保存できなければ停止し、未開始lease回復に任せる。
6. started markerを条件付き保存し、同一実行の保存が確認できた後だけ1回呼ぶ。
   応答が遅れたらもう一度上記残時間を確認する。
7. 成功/固定失敗を同じ権利でfinish。取得済み結果のDB保存だけを上限付き再試行する。

開始記録は呼出が実際に外部へ届いた証明ではない。marker直後の停止もOUTCOME_UNKNOWNになり得る。
call_phase=startedの別Workerに再呼出権はない。Workerは期限切れrunningを直接claimしない。
Provider SDK/HTTPレイヤーにも自動再試行を許さない。P5で実際の設定を検証する。
プロセス停止で結果を失った場合の自動再呼出はしない。可用性を犠牲にし、自動の重複課金を抑える初期方針。
外部サービス内部の課金exactly-onceは保証しない。利用者が新キーで再挑戦すれば新しい評価として課金され得る。

同じstartedを読んだだけで呼出さず、生存中executionの開始保存応答消失のみ確認継続可能。
terminalは既存結果を返す。lost_leaseは保存権喪失であり成功扱いにしない。
詳細な期限境界・送信中のcommitは [Transaction](p2/transactions.md)。

## P2-208 DispatcherとRecovery

Dispatcherは送信権取得後にSQS SendMessageを1回だけ行う。
成功後、同じ世代/未期限切れ送信権/PENDINGだけQUEUEDへ。
WorkerはPENDINGから先着claimできるため、遅い確認でCLAIMED/DONEを上書きしない。
送信成功か不明でもDB更新が失敗したら、権利切れ後に再送され得る。Provider重複はclaimで防ぐ。

Recoveryは1分周期、[WorkIndexと走査位置](p2/dynamodb-design.md)に沿って全3 partitionを巡回する。

| 判定順 | 状態 | 処理 |
|---|---|---|
| 1 | 対象/関連破損 | Provider未呼出、IntegrityError監視、業務更新なし、手動修復Gate |
| 2 | terminal | 無操作。古いindex/イベントは正常終了 |
| 3 | 非終端でdeadline到来 | T13でfailed、D DONE、現在active同期 |
| 4 | PENDING | next_at到来かつ送信leaseなし/期限切れならT07で送信。それ以外無操作 |
| 5 | QUEUED | claim_due到来かつE pendingならT10で世代+1、PENDINGへ |
| 6 | running/not_started | lease到来ならT11でpending、世代+1へ |
| 7 | running/started | lease到来なら保存済み終端を再確認し、未終端だけT12でOUTCOME_UNKNOWN |
| 8 | 上記期限前 | 無操作 |

古い候補/観測revの競合は現在状態を再取得し再分類する。旧観測を強制適用しない。
再投入したPENDINGはStreamsまたは同じDispatcherの予算内送信、失敗しても次周期で回収する。
terminal逆遷移、Attempt増殖、期限延長はしない。
DB/GSI障害中に15分内で収束する保証はない。復旧後deadline超過を検出して失敗に収束する。
関係破損は自動回復対象外。監視と安全な手動復元が完了するまで公開processing/500が残り得る。

## P2-209 初期設定・再試行責任

| 設定 | 決定値/理由 |
|---|---|
| Worker timeout / lease | 60秒 / 90秒、延長なし。正常Lambda終了に30秒余白 |
| Provider timeout / 開始必要残時間 | 最大40秒 / 50秒 |
| Evaluation deadline | 受付+15分。Frontend120秒停止と独立 |
| SQS visibility / batch / window | 360秒 / 1 / 0秒 |
| maxReceiveCount | 5 |
| Worker event source最大並列 / reserved concurrency | 2 / 2、通常on-demand poll。Provisioned Mode不使用 |
| Main queue / Worker DLQ保持 | 4日 / 14日 |
| Dispatcher timeout / send lease | 30秒 / 45秒 |
| QUEUED claim確認 | queued_at+120秒 |
| Recovery周期 / 新規処理停止 | 1分 / 残り5秒 |
| DB SDK retry | total_max_attempts=1 |
| Repository retry | 各論理保存最大3送信、5秒以内、jitter上限100/200ms。外側の実行時間を優先 |
| SQS SDK retry | total_max_attempts=1、connect/read各1秒。送信1回/権利 |
| 配送backoff | generation_attempts=nに対しB=min(300秒,10秒×2^(n-1))、待ち時間B/2〜Bの一様jitter |
| 配送回数の上限 | 追加の回数打切りなし、受付15分deadlineで終了。SDK内部再送なし |
| Provider retry | 0。SDK内部再送も0 |
| SQS handler結果 | terminal/stale/busy/missingはack、missingは計測。deadline_dueは回復で保存確認後ack。DB/破損/不正イベントはbatch失敗 |

SQS visibility360=6×60+window0、maxReceiveCount5はAWS推奨に合わせる。
AWSはreserved concurrency最低5も推奨するが、初期費用抑制を優先し、
唯一のSQS event source最大並列も2に制限する。throttle/滞留をP4で検証し、2での可用性を保証済みとしない。
[Lambda SQS設定](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)、
[最大並列設定](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html)

lost_leaseの場合は再読取りでterminal/新権利を確認して旧実行を終了する。
DBが確認不能ならbatch失敗。旧権利でProvider/finishを再試行しない。
busyをackした後のWorker停止はRecoveryで回収する。SQS再配送とDB保存再試行はProvider再試行ではない。
Recoveryが120秒で世代を進めるためvisibility360秒内でも新メッセージが先行し得るが、旧世代は無操作。
手動DLQ処理: 通知→安全なIDを取得→DBのowner/関連/terminal/世代/started/deadline確認→原因修正。
terminal/古い世代は業務再開せず隔離終了。現世代pendingだけ許可された担当者が元イベントを再投入できる。
runningはRecoveryに任せる。未知versionをその場で自動変換しない。全件無条件redriveは禁止。
既にstartedの評価を「再試行可能」へ編集しない。

## 確認と引継ぎ

R04〜R19を [机上確認](p2/P2_VERIFICATION.md) で照合。
P3はFake時計・Publisher障害注入で同じ分岐を検証、P4はStreams/SQS/Alarm/IAMの実際の挙動を検証する。
Streams障害時の回収、送信確認とWorker先着、結果不明時の課金方針はこのADRを変更せず実装者判断で変えない。
