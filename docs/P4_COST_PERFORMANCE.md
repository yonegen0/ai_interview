# P4：30人向けコスト・性能レビュー

> 2026-10-04時点の履歴。最新の設計・判定条件は
> [限定試験向けサーバレス最適化](P4_SERVERLESS_OPTIMIZATION.md)を参照。
> quota10は参考評価であり、最新計画の配備可否の必須条件ではない。
> AWS実性能未検証は後続試験として残す。以下の旧費用表・監視構成は現行予定値ではない。

## 採用する閉鎖dev構成

WorkerはReserved Concurrencyを設定せず、唯一のSQS mappingをMaximumConcurrency=2にする。
APIとDispatcherも予約なし。3関数とも512MB、timeoutはAPI15秒・Worker60秒・Dispatcher30秒を維持する。
DynamoDB On-Demand、SQS batch1/window0/visibility360秒、DLQ、Streams、毎分Recoveryを維持する。
Provisioned Concurrency、Provisioned polling、常時稼働サーバーは追加しない。
APIの既定rate/burstは20/30。4つの有効化フラグはfalseのままで、公開・負荷試験は別工程。

Reserved Concurrencyもquota上限の増加も、それ自体は追加料金を発生させない。
予約を外す目的は小さいquotaでの設定制約を避けること。SQS上限はAPI用容量を予約しない。
quotaが増えてもWorkerの処理上限を増やさない。

## 実測とモデルを区別する

2026-10-04、既存の正式ZIPに一致するコードとLinux依存を用い、400回の合成業務フローを測定した。
API entry、業務処理、DynamoDB adapter、FakeProviderを通すが、SDKは通信なしの合成保存先。
ローカルCPUはLambda512MBと同等ではなく、数値をAWSのDurationとして扱わない。

| ローカルLinux測定 | 平均 | p95 | p99 |
|---|---:|---:|---:|
| API（7操作を均等集計、2,800件） | 0.960ms | 1.716ms | 2.393ms |
| 回答受付 | 1.628ms | 2.309ms | 2.924ms |
| Worker | 11.070ms | 12.602ms | 14.783ms |
| 別プロセスのimport＋問題読込 | 621.773ms | 660.624ms | 677.149ms |

最後の行はAWS cold start実測ではない。LambdaのInitDuration、ネットワーク、API Gateway、
実DynamoDB時間は未計測。対象devは未配備で、CloudWatchに対象関数の実行データがない。

回答受付のSDK呼出しは3回、評価pollingは1回、Workerは10回。
SDK往復10msを**仮定**すると、回答受付p95相当は約32.3ms、30 RPSの平均必要枠は約0.97。
Worker2＋Dispatcher/Recovery用2を加え約5枠。1秒30件・2秒30件のwarmモデルは拒否なし。
SDK往復5/10/20/50/100ms、ローカルCPU時間1/4倍、他アプリ占有0/1/2/4枠を感度分析する。
約15 RPSとなる30人の2秒pollingに対し旧rate5は不足するため、20に調整した。
rate20/burst30は容量の保証や待ち行列ではなく、連続負荷を制限する目標値。

Worker上限2で30件の処理時間は約1.69秒（同じ10ms SDK仮定）。配送1秒、画面polling最大2秒などを
加え約4.8秒に到着窓0〜2秒を足したモデルとなる。これは実AWSの30秒SLOの証明ではない。
上限3/4はAPI側の余裕を減らし、現在のFakeProviderには必要性が認められない。

### 公開前に残る検証

warmでの通常・1秒集中・2秒集中の成立は、上記の通信遅延と共有負荷条件に依存する。
ローカルimport p95を初期化時間の代用にしたモデルでは、quota10・背景4枠の初回集中で
1秒30件中15件、2秒30件中5件が枠不足になる。AWSで同じ結果になると断定しないが、
新plan成功だけでcoldを含むSLOを合格扱いにしない。公開前に許可された小規模AWS実測で確認する。
完全同時30件はstress制約として別表示し、通常シナリオ全体の不合格理由には使わない。

通常負荷の成立をretryで補わない。Frontendのmutationと評価pollingは現在自動retryなし。
将来retryを追加する場合は、同一Idempotency-Key、同一payload、回数/総時間上限とjitterを必須とし、
新しいkeyで再送しない。今回Frontend・artifactは変更しない。

## 費用モデル（東京、USD/月、30日）

| 状態 | 無料枠除外 | 利用可能無料枠を仮定 |
|---|---:|---:|
| 配備後の閉鎖idle（4フラグfalse） | 3.52 | 2.51 |
| 稼働idle（RecoveryとSQS polling有効） | 4.92 | 2.73 |
| normal：3,000評価/月 | 6.41 | 3.22 |
| busy：30,000評価/月 | 12.88 | 6.85 |

これは請求実績ではなく、配備後の利用量仮定。最大同時利用者と月間利用者は別物。
30 MAU、月900通の認証メール、評価1件あたり20 API要求・80 RRU・120 WRU・30KBログを仮定。
Lambda課金時間はAPI0.2秒、Worker1秒、Dispatcher合計0.6秒/評価、Recovery0.3秒/分を見込む。
32 alarmに35課金metric参照があり、無料枠除外では月3.50ドル。custom metricsは稼働時間で按分。
ログ保持30日、S3合計0.1GB、DB累積保存増加、毎分RecoveryのDB要求を含む。
無料枠は共有アカウントで残っている場合だけ適用でき、期限付きcreditは含めない。
税、他アプリ、Frontend hosting/domain、実AIのAPI費用は含めない。

A（Reserved2＋SQS上限2）とB（予約なし＋SQS上限2）は同じ処理量なら同額。
C（上限なし）は空polling最適化で月約0.16ドル安くなる仮定だが、Workerが共有容量を消費し得る。
この小額削減のために上限制御を外さない。監視を削除した料金削減も今回行わない。

## 根拠

- [Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [SQS scaling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html)
- [HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [AWS公式Price List](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)：2026-10-04に東京の各サービス単価を取得。
- [CloudWatch料金](https://aws.amazon.com/cloudwatch/pricing/)、[Scheduler料金](https://aws.amazon.com/eventbridge/pricing/)

private証跡には元単価、式、各費目、無料枠条件、960件の性能感度分析、AWS読戻しを保存する。
保存planは閉鎖dev配備のレビュー対象であり、公開承認・実AWS性能保証を代替しない。
