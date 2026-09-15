# P2-210〜212 保持・Failure Matrix・Security

状態: 設計確定（2026-09-12）。実機運用未検証。
[ADR](../ADR-004-durable-evaluation.md)、[Transaction](transactions.md)、[確認・P3試験](P2_VERIFICATION.md)と対応する。

## P2-210 保持と削除

| 対象 | P3非公開・合成データの初期方針 | 本番前Gate |
|---|---|---|
| Worker/送信lease | 90秒/45秒、時刻で権利を制限。item削除ではない | P4時間・停止試験 |
| Evaluation処理deadline | 受付15分、超過は保存可能になった時点でfailed | P4滞留と回復試験 |
| Session/Attempt/Evaluation/Dispatch | API有効期間の自動終了なし、物理自動削除なし | P4で実個人データ投入前に保持日数・本人削除 |
| IdempotencyRecord | 自動失効なし。元成功応答の再現期間も無期限（記録を保持する間） | 期限後再確認の応答とキー再利用可否を公開契約と同時決定 |
| RecoveryCursor | 自動失効なし、走査位置の上書きのみ | P4運用監視 |
| DynamoDB TTL | 全itemで属性なし・未設定 | 物理削除とAPI有効期間は同一視しない |
| SQS | main4日、Worker DLQ/Stream failure queue14日 | 合成イベントのみで保持試験 |
| アプリログ | P4の初期保存30日、本文・生IDなし | 個人データ投入前に運用規定を承認 |
| Backup | P3は本番バックアップ保証なし | P4個人データ投入前に保存日数/アクセス/削除台帳/復元後削除を決定 |

本番保持日数を未決のまま実個人データを投入しない。担当工程P4、判断主体プロジェクト所有者。
P3は合成回答/合成subのみで進められる。P4に実DynamoDB試験を送る場合もこの境界を維持する。
本人削除ではSessionだけ削除して関連を残す案を採用しない。削除後の冪等再現とBackupからの復活防止を先に仕様化する。
初期TTLなしは削除機能実装済みや無期限保管の本番承認を意味しない。
lease/deadlineと保持期限を共通expiresAtで扱う案を見送った。確認R16/R17/R20、P4停止条件へ引き継ぐ。

## P2-211 Failure Matrix

以下のR番号はそのままP3試験IDとする。公開欄はGETまたはPOSTの観測。
「課金0/初回」はこの障害による追加のProvider自動呼出がないという意味で、外部課金exactly-once保証ではない。
手動対応の「再確認」は同キー同本文。新キーでの再挑戦は別Attemptで追加課金され得る。
全行で本文・生例外はログに出さない。

| ID/位置 | 保存状態・公開 | 自動回復/期待状態 | 手動対応 | Provider/課金 | 検出 |
|---|---|---|---|---|---|
| R01 同キー並列POST | 1 Tx成功、I固定。全成功応答同一 | I再取得→元201/202/200 | 通信不明時再確認 | 作成/次問0、回答初回のみ | IdempotencyReplay/DBConflict |
| R02 別キー回答/Next競合 | S.rev勝者のみ。敗者は現在状態に応じ409 | I優先→業務再判定、部分保存なし | 現在質問再取得 | 採用回答の初回のみ | StateConflict |
| R03 commit前拒否 | 新規保存0、固定500または証明済業務409 | 上限付きDBretry | 再確認 | 0 | DBError |
| R04 commit後応答消失 | 5件保存・公開processing、POSTは不明の場合あり | I確認で元202。配送は独立 | 再確認 | 初回のみ | AcceptanceUnconfirmed/Replay |
| R05 SQS失敗/確認失敗 | PENDING、公開processing | send lease/next_at後再送、claim後は更新拒否 | 滞留通知でDB/SQS確認 | 初回のみ、SQS重複可 | DeliveryFailure/PendingAge |
| R06 QUEUED前Worker完了 | E terminal/D DONE/該当S同期 | 遅いconfirmはobsolete、巻戻りなし | 不要 | 1回のみ | ObsoleteDelivery |
| R07 QUEUED起動漏れ | pending/QUEUED、processing | claim_due→世代+1→PENDING→初回評価 | 継続滞留なら基盤確認 | 初回のみ | QueuedAge |
| R08 重複/古い/順不同/DLQ | 状態は任意 | terminal/stale/busyは無変更ack。現pendingだけclaim | 無条件redriveせず状態照合 | 自動再呼出なし | DuplicateSuppressed/DLQ |
| R09 claim後marker前停止 | running/not_started、processing | lease後世代+1/pending→初回評価 | 通常不要 | 初回のみ | ExpiredLease |
| R10 marker後実送信前停止 | running/started、processing | lease後failed/OUTCOME_UNKNOWN | 利用者判断の新Attempt | 0回でも失敗になり得る | OutcomeUnknown |
| R11 Provider処理中/成功直後停止 | running/started、processing | lease後failed/OUTCOME_UNKNOWN | 新Attemptは追加課金を説明 | 実際の課金不明、再呼出なし | OutcomeUnknown |
| R12 finish失敗/応答消失 | runningまたはterminal | 同じ結果保存のみretry、terminal確認。結果喪失はR11 | DB障害対応 | 再呼出なし | FinishRetry/DBError |
| R13 Recovery対Worker/Recovery | 観測rev/lease競合 | CAS勝者のみ、敗者再分類。旧Worker開始/finish拒否 | 反復異常時時刻調査 | 新権利もstartedなら呼ばない | LostLease/DBConflict |
| R14 Session別active | 過去E/D、Sは別Attempt/null | S非一致をTxで確認、E/Dだけ終端 | 不要 | 過去評価の再呼出なし | ProtectedActive |
| R15 参照欠落/owner不一致 | 不整合、公開processingまたは固定500 | Provider未呼出。候補を計測し次へ、次巡再確認 | 隔離・監査後の承認済修復。勝手なowner修正禁止 | 0追加 | IntegrityError |
| R16 deadlineと予定逆転 | 非終端、processing | due=minで期限検出、failed/DEADLINE_EXCEEDED | DB停止中は復旧待ち | 再呼出なし | DeadlineOverdue |
| R17 Frontend120秒停止 | Backend処理継続/終端、保存要求残る | UI停止をキャンセルにしない | 同キー手動確認は元202、その後GET最新状態 | 再呼出なし | EvaluationLatency/Replay |
| R18 古いGSI/多ページ | baseは更新済または未処理 | 強整合再検証、Cursor継続で後続処理、次巡で旧候補再訪 | SweepLag時容量/破損確認 | 権利検証後のみ | RecoverySweepLag/Heartbeat |
| R19 不正イベント/未知version | DB未変更、公開に新状態なし | batch失敗→DLQ、Provider禁止 | 正式版対応を承認後、元状態を照合 | 0 | InvalidEvent/DLQ |
| R20 process/保存先再起動 | 永続item/I/Feedbackが残る前提 | 起動後GET/元応答再現、必要な回復 | 選定環境の復旧手順 | startedの再呼出なし | StartupFailure/Persistence |
| R21 Provider不正/過大結果 | running→固定failed | INVALID_RESULT/RESULT_TOO_LARGEを保存。本文切詰めなし | 品質/設定を調査 | 初回のみ | EvaluationFailure |
| R22 DB/GSI長期障害 | processingがdeadline超過し得る | 復旧後失敗収束、期限内完了保証なし | 基盤復旧、合成試験で確認 | startedは再呼出なし | DBError/Throttle/SweepLag |

再試行で失敗を隠す案と、GETで回復を進める案は見送った。
結果不明の自動再呼出なしを採用し、完了率と課金リスクのトレードオフを明記する。

### 監視の初期値・測り方

| メトリクス | 取得方法 | P4初期通知/対応 |
|---|---|---|
| DLQ件数 | SQS ApproximateNumberOfMessagesVisible（2隔離Queue別） | >=1で調査 |
| PendingAge/QueuedAge | Recoveryでbase created_at/queued_atとの差、最大値 | 120秒超の候補で警告。配送backoff中も観測 |
| ExpiredLease/DeadlineOverdue | due候補のbase期限比較 | 1件以上で記録、2周期連続で通知 |
| RecoveryHeartbeat | Scheduler経路が3 partitionを試行しcheckpointできた時にEMF出力 | 3分欠落、欠測を異常扱い |
| RecoverySweepLag | Cursor.cycle_started_at/完了周期 | 1巡3分超で通知。heartbeatだけで健全扱いしない |
| Lambda障害/throttle/IteratorAge | AWSメトリクス | エラー1以上、throttle1以上、Stream遅延120秒超を5分窓 |
| DB障害/throttle | SDK安全分類のEMF＋AWS Table/GSIメトリクス | 5分窓1以上 |
| OutcomeUnknown/IntegrityError/InvalidEvent | 固定分類のEMF | 1以上で通知 |
| 評価失敗率 | 終端成功/失敗カウンター | 15分10件以上で失敗率20%超。少数でも結果不明は別通知 |
| latency/duplicate/lost lease | 固定分類EMF | 傾向を確認、owner/IDをdimensionにしない |

GSI候補からの年齢は全件の厳密な最古値とは限らない。巡回遅延と欠測も合わせて監視する。
独自EMFは既存標準JSON出力で足り、監視のためだけの新ライブラリをP2で追加しない。
Alarm配送先と疎通はP4の開始条件であり、文書で通知済みと扱わない。

## P2-212 認証・権限境界

JWT署名/issuer/audience/exp等の検証責任はP4のHTTP API JWT Authorizer。
AuthorizerだけでToken種別を区別できるとは仮定せず、以下のadapter確認を追加する。
[AWS JWT Authorizer仕様](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
API adapterは信頼したAuthorizer contextだけからsubを取得し、access tokenのtoken_use=access、
許可client_idを照合する。本文/ヘッダーの自称subを優先しない。任意HTTPからclaims fixtureを作れない構成にする。
Cognito Email OTPの実Token・scopeはP4/P6で確認し、未確認custom scopeを前提としない。
Applicationは主体とID/入力を検証、RepositoryはUSER#subの直接取得で本人認可する。
他人IDは既存404。内部Eventのownerも信頼しきらず、PK・全参照先owner・逆参照を照合する。
同一Lambda roleは複数利用者を処理するのでIAMだけで本人認可できるとはしない。

### IAM表（P4で作成、P2では作成しない）

物理設計がCAS Putを採用したためUpdateItem/DeleteItem/Scanは不要。
Transaction API名そのものをIAM actionとして列挙せず、
PutItem/GetItem/ConditionCheckItemで制御する。
[AWS Transaction IAM](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html)

| 主体 | 必要な操作 | 対象リソース/境界 |
|---|---|---|
| API | dynamodb:GetItem、PutItem | 対象Table ARN。PutはEnclosingOperation=TransactWriteItemsに限定。Query/SQS/Secret不可 |
| Worker | dynamodb:GetItem、PutItem、ConditionCheckItem | 対象Table ARN。Put/ConditionCheckはTransaction限定 |
| Worker event source | sqs:ReceiveMessage、DeleteMessage、GetQueueAttributes | main Queue ARNのみ。隔離Queue redrive権限なし |
| Dispatcher | dynamodb:GetItem、PutItem、ConditionCheckItem | 対象Table ARN。Cursor以外のPutはTx、Cursorの単独CAS Putを許可 |
| Dispatcher回復検索 | dynamodb:Query | 対象WorkIndex ARNのみ。Scanなし |
| Dispatcher Streams | dynamodb:DescribeStream、GetRecords、GetShardIterator | 設定Tableのstream ARN群のみ |
| Dispatcher Stream一覧 | dynamodb:ListStreams | このactionはリソース単位制限非対応なのでResource=*。他のactionとstatementを分離する |
| Dispatcher送信/失敗宛先 | sqs:SendMessage | main QueueとStream failure queueの各ARNだけ |
| Scheduler execution role | lambda:InvokeFunction | 対象Dispatcher ARNだけ。信頼はscheduler.amazonaws.com、source account/対象schedule group制約 |
| Lambda共通Logs | logs:CreateLogStream、PutLogEvents | P4で先に作成する各専用LogGroup/streamのみ。CreateLogGroup不要 |
| P5 Workerのみ | secretsmanager:GetSecretValue | 採用時の特定Secret ARNのみ。P3/P4 Fakeには与えない |

API Gateway→API Lambdaはresource policyで対象API/stage/routeのSourceArnに限定する。
Event source mapping管理・Table作成・IAM変更・手動redriveは配備/運用担当の別roleで、実行roleへ付けない。
Stream ARNへのListStreams等の対応は [AWSサービス認可表](https://docs.aws.amazon.com/service-authorization/latest/reference/list_dynamodb.html) を基準とする。
Queueは初期SSE-SQS、TableはAWS所有キーの暗号化。独自KMS keyを先回り追加しない。
後に顧客管理KMSを選ぶ場合だけ必要なDecrypt/GenerateDataKeyとkey policyを該当工程で再設計する。
Secretも今は作成しない。P5のWIF/Secret最終選定Gateを維持する。

### ログ・イベント・手動対応

許可: UTC時刻、固定イベント名/失敗分類、duration、件数、generation、lease_version、
random correlation ID、必要時のsub/resource IDのSHA-256相関値（これも個人関連情報として管理）。
禁止: raw sub/メール/回答/質問全文/Feedback/Prompt/Token/Secret/HTTP headers/SDK例外本文/
Stream画像/SQS本文/Idempotency body。SDK debug/HTTP bodyログは無効。例外のstr/reprを出さない。
schemaエラーも入力値を含む詳細を出さず固定分類とする。権限不足を業務不存在に偽装しない。

不正イベントはR19、両E/D不存在はmissingを計測してack、片側/関連欠落はR15で失敗。
手動修復は通知→対象特定→読取り監査→承認→限定変更→関連再確認の順。
自動で別ownerに探索・修復・terminal解除をしない。通常運用が破損itemを作らないことはP3原子性試験で確認する。

P4/P6の実Token試験: 無署名/改竄/他issuer/他client/期限切れ/ID token拒否、正当Access Token、
別人の全Route IDと同キー、停止利用者の既発行Token扱い、refresh失敗、
logout/利用者切替でCacheとsessionStorageを混ぜないこと、CORSの必要Headerと許可Origin。
P3本人fixture成功を署名検証済みとは呼ばない。
決定理由は主体を各信頼境界で確認し、便利な管理権限を実行roleへ持たせないため。
確認R08/R15/R19、P4/P6認証Gateへ引き継ぐ。
