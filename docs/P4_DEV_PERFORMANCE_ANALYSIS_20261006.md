# P4 dev 2026-10-06：Closure後の性能分析

正式ステータスは`P4_DEV_CLOSED_PERFORMANCE_REVIEW_REQUIRED`。
第6Closure applyは承認されたsaved planを1回だけ実行して成功した。
Stateは50 resources/serial11、API disabled、Worker/Streams Disabled、Scheduler DISABLED、
validation Alarm0、active lockなし、State外dev resourceなし。修正版Artifact・Lambda publish版2・
4aliasを保持する。`POST_DEPLOY_PERFORMANCE_VALIDATION_REQUIRED`は維持する。

今回の変更は運用ドキュメントだけ。閉鎖後の分析では再Enablement、新負荷試験、新plan、
Terraform/application変更、Artifact build/upload、memory/concurrency/PC変更を実行していない。

## Formal gateとPractical usability

Formal performance gateの`API p95 <= 2秒`は**FAIL**のまま。
Scenario CはPOST answers30件とGET evaluation33件、計63件のnearest-rank p95。
昇順60番目の値が2003.466msで、閾値超過は3.466ms。2秒超の4件はすべてPOST。
POST30件だけでもp95=2065.312msであり、pollingとの集計方法だけで問題が消えるものではない。
後付けで閾値・percentile・母集団を変更してPASSにしない。

| Scenario | HTTP成功/件数 | 全API p95 | POSTだけのp95 | 30評価の完了確認 | API cold REPORT数 |
|---|---:|---:|---:|---:|---:|
| A：9秒分散 | 60/60 | 162.719ms | 182.019ms | 15.675秒 | 0 |
| B：2秒分散 | 60/60 | 122.254ms | 136.951ms | 8.814秒 | 0 |
| C：1秒分散 | 63/63 | 2003.466ms | 2065.312ms | 9.283秒 | 5 |
| D：同時・参考 | 67/67 | 2171.101ms | 2177.678ms | 9.821秒 | 12 |

Practical usabilityでは、有限のFakeProvider試験で120評価が完了し、
429/5xx/timeout=0、DLQ=0、SQSは最終全0、backlogの持続増加なしだった。
A/Bの分散利用は良好。Cでも評価完了は30秒基準に余裕があり、主な問題は受付時のcold tail。
限定dev利用の機能・処理能力には肯定的な証拠があるが、coldを含む応答SLOを満たす公開運用の
受入PASSではない。各scenario1回、30人、FakeProviderのみで、実AI・長期負荷・統計的安定性は未検証。
D単独の悪化は全体FAIL理由としない。DDB throttleは欠測を0とみなさず、実用上の問題は観測されなかったと扱う。

## Cの遅延内訳：既存ログを追加解析

既存API LambdaのSTART/REPORTとEMF `ApiDuration`をlog stream内で対応付けた。
Cの63呼出をすべて対応付け、`Init Duration`がある5呼出は次の範囲だった。

| 内訳 | 最小 | 最大 |
|---|---:|---:|
| Init Duration | 1260.070ms | 1312.990ms |
| Invoke Duration（REPORT） | 548.410ms | 594.350ms |
| 業務ApiDuration（同じ呼出のEMF） | 137.055ms | 175.915ms |
| Invoke − ApiDuration | 411.355ms | 428.877ms |
| 同じ呼出のInit + Invoke | 1851.770ms | 1874.390ms |

[`aws_runtime.py`](../backend/src/interview_backend/aws_runtime.py)では、
`api_handler → _invoke → build_entry → ApiEntry.__call__`の順に実行する。
`build_entry`はlru_cacheで環境内再利用するが、初回はAwsSettings読込、DynamoDB SDK client生成、
question bank読込とモデル検証、Application/Handler構成を行う。
`ApiDuration`の開始点はその後の`ApiEntry.__call__`内なので、初回構成時間はこの業務metricから外れる。
約411〜429msの差には初回構成・wrapper・telemetry等が含まれる。
SDK client生成やquestion bank等の個別寄与は既存ログで分離できず、特定の処理だけが原因とは断定しない。

cold呼出はInitだけでも約1.3秒、Invokeを含めると約1.85〜1.87秒に達しており、2秒Gateまでの余裕が小さい。
AWSはInitとInvokeを区別し、静的初期化の依存・コード量と接続準備が遅延要因になると説明している。
[AWS Lambda lifecycle / static initialization](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)

Cを含む07:47 JSTのAPI-wide1分bucketは123件で、Gateway Latency最大2078ms、
IntegrationLatency最大2076msだった。後続Dの準備呼出も含むためCだけのpercentileではないが、
AWS integration側でも2秒超が観測されており、clientだけの遅延とは言えない。
このbucketのp95約113msをCの合否値に置き換えない。
[HTTP API metricの範囲と1分粒度](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html)

測定clientは正式`auth_e2e.Api`のurllib。実測はHTTP request構築・TCP/TLS・response読込/JSON処理を含む。
ローカルstdlibの`AbstractHTTPHandler.do_open`は`Connection: close`を設定しており、
永続connection poolを使っていない。browser fetchのconnection再利用と完全に同じ条件ではない。
これは外側の遅延候補だが、Gateの結果を無効にする根拠ではない。
[CPython 3.14.4 urllib実装](https://github.com/python/cpython/blob/v3.14.4/Lib/urllib/request.py)

## 推定の確度と限界

- 確認済み：cold Init5件、同じLambda呼出の初回Invoke時間、業務timerの外にある約0.42秒、
  全63呼出の成功、Gateway integration最大2.076秒、Worker2で全30評価が完了。
- 有力な説明：新しいAPI実行環境のInitと初回構成、最初のDDB接続等の業務処理、
  Lambda service/integrationの外側の処理、client通信が積み重なり、cold tailが2秒を越えた。
- 未確定：HTTP Gateway requestIdとLambda requestIdの直接対応、SDK/読込/モデル検証の個別寄与、
  DNS/TCP/TLSやLambda service準備の時間。既存access logにはintegration latencyやLambda requestIdがない。
- SQS、Workerの処理能力やAPI throttleの引上げを必要とする証拠は今回得られていない。
  API同時実行の1分最大値はC8、D30、Workerはいずれも2。拒否・timeout・継続backlogはない。
- 小標本のp95は数件のcold呼出の順序に敏感で、3.466msの余裕/超過に再現性の保証はない。
  クライアント/AWS clock差はmonotonic経過とAWS内timestamp同士で処理し、mixed-clock値は判定に使わない。

## 改善案：今回の実装変更なし

1. 次の別作業では、APIに不要なWorker/Dispatcher依存のimportと、初回`build_entry`の各工程を解析し、
   役割ごとのimport範囲・初回構成量を減らす候補を検討する。auth/owner isolation/冪等性を維持する。
   初期化をInvokeからInitへ移すだけではcoldの総時間は減らないため、metricの見かけの改善で済ませない。
2. 同じGate・同じ30人Cを主評価として、warm/cold、POST/poll、client/IntegrationLatencyを分離する
   次回検証計画を作る。browser相当connection再利用との比較も別測定として扱い、元のFAILを改訂しない。
3. memory/CPUの比較は別承認の計画と費用評価が必要。今回512MiBを変更しない。
   concurrency/throttle増加やPCは今回の改善実装に含めず、特にPCの固定費をdevの閉鎖目的と比較する。
4. いずれの次回試験も[条件付き自動Closure承認](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)を同時に含め、
   成功/失敗にかかわらず安全なClosureを完了してから報告する。

追加の詳細metrics、REPORT/EMF対応表と元の生ログを保存しない抽出結果は、Git管理外の
`.p4-artifacts/apply-20261006-02/performance-analysis.private.json`に保存した。
閉鎖applyと読戻し証跡も同じprivate directoryに保存し、認証token・OTP・回答本文は掲載していない。
