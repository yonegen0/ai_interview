# P4 dev：限定試験向けサーバレス最適化

2026-10-05。管理者が見守り、合成データだけを使う最大30人の限定試験用。
実装・モデル・planの検証とAWS実測を区別する。今回の終点はsaved planの監査。
apply・公開・mapping/Scheduler有効化・AWS負荷試験は別途承認が必要。
完了条件を満たした場合の正式ステータスは
`P4_DEV_SERVERLESS_FREE_TIER_PLAN_VERIFIED_PENDING_APPLY_APPROVAL`、
実性能は `POST_DEPLOY_PERFORMANCE_VALIDATION_REQUIRED` とする。
未監査planやoffline成功だけで正式ステータスを変更しない。

## 構成と監視

HTTP API/JWT → API Lambda → DynamoDB On-Demand → Streams/Dispatcher →
SQS Standard → Worker。毎分Scheduler Recovery、Cognito/SES認証、SNS通知、月額Budget。
LambdaはVPCなし、512MB、x86_64、On-Demand、全関数Reserved未設定、
Tracing `PassThrough`。Timeout API15秒／Worker60秒／Dispatcher30秒。
SQS batch1/window0、Worker MaximumConcurrency2、visibility360秒。
API default route rate20/burst30。PITR OFF、S3 versioning維持。
NAT、EC2/ECS/Fargate、RDS、ALB/NLB、Provisioned Concurrency/pollingはない。
Frontendはstatic exportを維持し、配信資源を追加しない。

devの4フラグが全falseならalarm0件。いずれかtrueなら14件を作成してから処理を有効化する。
独立した監視無効フラグはない。testは従来32件を維持。
通知topic/subscription/policyは閉鎖中も維持。単一alarmのcount化はmovedでtestアドレスを移行する。

| alarm suffix | 件数 | threshold/operator | period/statistic/評価周期 | 欠測 |
|---|---:|---|---|---|
| 各関数Errors | 3 | 1以上 | 300秒/Sum/1 | 正常 |
| 各関数Throttles | 3 | 1以上 | 300秒/Sum/1 | 正常 |
| dlq-worker、dlq-stream | 2 | 可視1以上 | 60秒/Maximum/1 | 正常 |
| 各関数IntegrityError | 3 | 1以上 | 300秒/Sum/1 | 正常 |
| OutcomeUnknown | 1 | 1以上 | 60秒/Sum/1 | 正常 |
| RecoveryHeartbeat | 1 | 1未満 | 60秒/Sum/3 | 異常 |
| RecoverySweepLag | 1 | 180秒超 | 60秒/Maximum/1 | 正常 |

Scheduler無効時はHeartbeatとSweepLagのactionsを無効にする。
alarmは存在時間と参照metric数で課金される。actions無効だけでは無料にならない。
14件は全て単一metric、標準解像度。metric filter/dashboard/composite alarmを追加しない。
既存ZIPのEMFは維持するため、alarmを削除してもEMF課金は別に残る。
[CloudWatch料金](https://aws.amazon.com/cloudwatch/pricing/)

DBError、InvalidEvent、InvalidConfiguration、InternalInvocationFailed、PendingAge、
QueuedAge、ExpiredLease、DeadlineOverdueは既存EMFと安全なログ分類を管理者が確認する。
IteratorAgeは標準Lambda metric、評価失敗率は試験結果から確認する。
HTTP業務エラーがLambda Errorsへ計上されない場合もある。業務結果・DB throttle・
対象評価の終端・backlogも必ず確認する。異常時は新規負荷を止めて調査する。
無人の日常利用に移る前に、滞留・回復・業務エラー監視を再設計する。

終了時は新規負荷停止→対象評価の終端確認→main queue可視/処理中/遅延と両DLQ確認。
queue件数は近似値なので複数回確認する。残留や異常があれば監視を維持する。
devのLambda3個とAPI access logは7日、testは30日。本文・JWTは追加記録しない。

## 月次費用

東京、USD、30日720時間。全件監査前の計算モデルで、請求実績ではない。
前後とも同じ補正済み使用量で比較し、構成削減と稼働時間削減を分ける。
稼働時DynamoDB .01GBを仮置き。閉鎖初回はデータ0。
S3全version実読戻しはartifact19,015,751bytes＋State履歴93,484bytes、合計19,109,235bytes。
両bucketにmultipart残存はない。一律Lifecycleや削除は追加しない。
無料枠の共有残量は未確認で、「利用可能と仮定」の列でのみ控除する。

| シナリオ | 旧：無料枠なし | 新：無料枠なし | 旧：対象無料枠利用可能 | 新：対象無料枠利用可能 |
|---|---:|---:|---:|---:|
| closed idle | 3.50048 | 0.00048 | 2.50048 | 0.00048 |
| active idle、720h | 4.917 | 2.812 | 2.714 | 0.614 |
| 3,000評価、720h | 6.410 | 4.302 | 3.174 | 1.074 |
| 30,000評価、720h | 12.875 | 10.747 | 6.495 | 4.395 |

旧公開概算3.52/2.51、4.92/2.73、6.41/3.22、12.88/6.85との差には
SNS/Budget .01仮置きの撤去、転送無料枠、ログ保存と取り込みの分離などのモデル補正が含まれる。
その差をTerraform変更による削減として数えない。
旧alarm32件は35metric参照で$3.50、10適格alarm metric無料を仮定すると$2.50。
新closedは0件$0、新active14件は$1.40/$0.40。
閉鎖で$3.50/$2.50、稼働で$2.10を削減する。
7日保持の削減は保存費だけ。取り込み費は変わらない。

| 費目 | 計算入力・根拠 |
|---|---|
| Lambda | 20API/評価、API.2秒、Worker1秒、Dispatcher6×.1秒、Recovery.3秒/分。全て課金Durationの仮定 |
| HTTP API | 20requests/評価。12か月枠・新account creditは恒常的無料として控除しない |
| DynamoDB | 80RRU/120WRU/評価、Recovery4.5RRU/6WRU/分、20KB/評価増加。GSI・transactionsを含む予算 |
| SQS | 5poller×20秒に1Receiveの空poll仮定、実処理3×1.05requests/評価。2並列はpoller2台を意味しない |
| S3 | 現行・非現行versionの全保存量。正式ZIP/versionと監査証跡を保持。月次PUT/GETを根拠なく置かない |
| Logs | 5KB/Recovery、30KB/評価。取り込みと7日保持による保存量を別計算。通常検索0、試験検索は追加 |
| Custom metrics | 名前＋Project/Environment/Componentごとのidentityと発行時間。正常系8identityの仮定。エラー発行は追加 |
| Alarms | 参照metric数×存在時間。新dev14、closed0。旧32/35。metric数の無料枠はcustom metricsと別 |
| Cognito/SES | 30MAU、月900email、10KB/email。最大同時30人とは別の月間仮定 |
| Scheduler | enabled_hours×60 invocations。東京SKU `29C3758CBCYNXH8B` $1.25/百万、無料14百万を利用可能と仮定 |
| SNS/Budgets | baseline alarm通知0件、SNS0。Budget監視/email通知無料、Report/Actionsなし |
| 転送 | API5KB/request、同一region有料経路なしの仮定。東京→External SKU `9ESU2G5WSY6FMZR3` .114/GB、共有100GB枠は仮定 |
| IAM/alias/permission等 | 独立課金なし。連携先サービスの費目へ対応付ける |

公式Price Listのservice、region、SKU、usage type、unit、price、取得日時はprivate料金証跡に保存。
metricの無料計算は「月換算数−10」ではなく、適格identity10個の共有枠と発行時間で計算する。
正常系8identity以外の発行もあり得る。追加の有料identityは1発行時間あたり約$.3/720。
無料枠：Lambda100万requests/40万GB-s、SQS100万requests、DynamoDB保存25GB、
CloudWatch custom metrics10・標準alarm metrics10・Logs5GB、Cognito条件付き枠。
accountの適格性・共有残量は未検証。期間限定creditを恒常的無料化とは扱わない。
税・支援契約・Frontend・ドメイン・外部AI費用・他用途は含まない。
DBにTTLがないため、3,000評価で.06GB/月、30,000で.6GB/月が翌月以降も累積する。
閉鎖後も保存済みDB・ログ・S3、読戻し/planの一時API費用は残る。

120h/360hだけ稼働する補助表はprivate計算に保存する。
Recovery・polling・alarm存在時間を短縮し、同じ評価数の従量費を時間と共に減らさない。

| 新構成・限定稼働 | 無料枠なし | 対象無料枠利用可能と仮定 |
|---|---:|---:|
| 120h idle | .471 | .103 |
| 360h idle | 1.408 | .307 |
| 120h・3,000評価 | 1.962 | .563 |
| 360h・30,000評価 | 9.342 | 4.088 |

Budget月$10、ACTUAL80%/100%超、FORECASTED100%超、既存承認済みemail、account-wide。
通知遅延があるため支出上限ではない。
[Budgets料金](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)

### Provisioned・Frontend・arm64の比較

On-Demandを維持する。Provisioned無料25RCU/25WCUはaccount内のテーブルとGSIの共有枠。
回答受付transaction内の複数item writeは各1KB切上げ×2、GSI更新は別capacityが必要。
Worker claim/finish/stateとWorkIndex、Recovery query/pollingも加算する。
仮に120WRU/評価を1秒間に30評価で消費すると3,600write units相当であり、
月平均から25WCU内と判定できない。実itemサイズ・base/GSI配分・集中需要が未測定なので採用しない。
読取は4KB切上げ、一貫性とtransaction倍率を含めて別に計算する。
公式Price ListのRCU/WCU-hour単価もprivate比較へ保存する。

Frontendは既存static exportが候補のS3+CloudFrontに適合する。
CloudFront従量課金の無料枠とFree planの1百万requests/100GB等は方式ごとに条件が異なる。
Free planのquota、利用可能機能、超過時の挙動、S3 creditを選択時に再確認する。
今回は配信資源も公開経路も追加しない。
[CloudFront料金](https://aws.amazon.com/cloudfront/pricing/)
arm64は同一GB-sなら約20%低いcompute単価が候補。実時間比が1.25を超えると利点を失う。
native依存（pydantic-core等）の対応・再build・正式artifact再監査が必要で、今回の固定ZIPは変更しない。

## 30人の理論性能

ローカルLinux計測はCPUだけの参考値。回答p952.309ms、Worker12.602ms、
API各要求の保守値2.393ms。別process import660.624msはAWS cold start実測ではない。
SDK往復10ms、client/API Gateway通信50ms、配送1秒、初期化660.624msの仮定でイベントモデルを使う。
回答POST→初回評価GET→直前応答後2秒polling→feedback GET→session GET/次問POSTを計数する。
SDK回数は回答POST3、評価/session GET1、feedback GET2、次問POST3。既存storage実装から確認する。
同一warm環境は再利用し、coldは各環境の初回だけ加算。Worker2laneの初期化も初回だけ。
Dispatcher/Recovery等4枠＋Worker2枠を背景占有に確保する。

通常5RPS/60秒、30人の2秒polling、30回答を1秒/2秒に分散、
回答10人＋既存polling10人＋結果/次問取得10人の混在を合否対象にする。
完全同時30回答はstress参考。別の30pollerに30回答を追加した負荷は上限外の感度評価で、
rate20による拒否が出るため成功とは扱わない。
quota1000が主判定、quota10は参考。retryなし成功率を評価し、受理分p95だけで判定しない。

上記入力でquota1000の通常・polling・1秒/2秒集中・混在はwarm/cold代理とも
`MODEL_PASS_WITH_ASSUMPTIONS`。30件結果取得はwarm約3.25/4.21秒、cold代理約5.67/6.28秒。
quota10はwarm混在とcold代理のpolling/集中/混在で拒否が出る。現在の配備可否の必須条件にはしない。
これらはAWS成功率やcold startの証明ではない。
合否対象のモデル上の必要concurrency上限はwarm11、cold代理41、quota1000との差は989/959。
別用途の占有が仮定4枠を超える場合は再計算する。stressはcold代理54枠で別表示する。

SDK/cold/配送時間の感度、各ケースのp95・拒否・30件結果取得時間・必要concurrencyはprivate結果へ保存する。
通信SDK10msのWorker計算は15×(.012602+10×.010)=1.689秒。
配送・初期化・回答・polling・結果取得を足すので、この値だけで30秒SLOを証明しない。
API境界の保守式は `.002393+3×SDK+init+network≤2秒`。
SDK10ms/network50msならinitの上限は約1.918秒。
30件境界の保守式は `集中時間+回答時間+dispatch+delivery+worker_init+15×Worker時間+poll2秒+結果GET時間≤30秒`。
この式はモデルの仮定からの上限で、AWS jitterやCPU差は含まない。
HTTP API stage default設定は各routeの既定値、route overrideとaccount共通制限は別。
rate20はAPI全体の厳密な費用上限ではなく、throttlingはbest-effort。
[HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)

## 後続AWS測定手順（今回は実行しない）

apply・有効化・試験の承認後、CodeSha256固定ZIP一致、512MB/x86_64/Worker2、JWT、
承認済みorigin、最大30テストaccount、合成データ、14alarm通知経路、開始時DLQ/異常なしを確認。
credential/JWTはメモリ内のみ。当日の単価で上限費用を事前計算する。

上限：30人、1,000評価、20,000HTTP要求、60分、各集中シナリオ反復最大3回。
通常5RPS60秒、30人polling、30回答/1秒・2秒と結果取得までを測定する。
warmとInit Durationで確認したcoldを分離し、観測できないcoldは未検証とする。
coldを作る無断deploy・設定変更はしない。完全同時stressは別表示。

API別/全体p50/p95/p99、成功/429/4xx/5xx/timeout、Init Duration/Duration、Errors/Throttles、
table/GSI throttle、queue可視/処理中/遅延/DLQ、評価受付→終端、最初の送信→全30結果取得、
retryなし成功割合・観測件数・サンプル不足を保存する。本文・JWTは保存しない。
正常系合格はAPI p95≤2秒、全30結果取得≤30秒、429/5xx/timeout/評価失敗0、
試験起因DB throttleなし、backlog解消・継続増加なし、DLQ/整合性/結果不明なし。
異常時は新規要求停止、進行中を観測して原因情報を保全する。再試行成功で初回失敗を消さない。
