# GPT-6 Luna Provider — 実装・承認境界

2026-10-08。実OpenAI呼出し、Credential登録、AWS apply、有効化、S3 uploadは今回行わない。
既存のCoaching V2/Recovery/4 handler共通ZIP/61資源を維持する。

## Providerと呼出し契約

`evaluation/selection.py`のWorker専用選択で既定はFake。OpenAIは
`INTERVIEW_AI_PROVIDER=openai`と`INTERVIEW_OPENAI_ENABLED=true`の両方が必要。
modelは`gpt-6-luna`固定、Responses API、standard/low、store=false、background=false、tools=[]。
effortはlow/mediumをサーバー設定で比較できる。temperatureは送らない。
max_output_tokens既定4096、設定範囲1024〜8192。reasoningを含む上限であり、実モデルで調整する。
[モデル](https://developers.openai.com/api/docs/models/gpt-6-luna)と
[reasoning](https://developers.openai.com/api/docs/guides/reasoning)を確認した。

既存固定developer指示と永続CoachingInput由来のuser JSONを分離する。
Question ID/owner/Session/Attempt/Evaluation ID/JWT/emailをメタデータとして送信しない。
本人回答そのものの個人情報を自動削除したとは扱わない。
過去AIの評価/exampleは送らず、AI質問は履歴の文脈としてのみ扱う。
`interview-coaching-v2`、V2の8required項目・各0〜10点・nullable・additionalProperties=falseを維持。
合計/減点/rankはBackendで計算し、400 code points/最大3回答/V1互換を維持する。
V1のoptional exampleAnswerはAPI出力schemaでnullableとし、nullを旧公開応答では省略する。
[Structured Outputs契約](https://developers.openai.com/api/docs/guides/structured-outputs)に沿い、
Pydanticと既存重複/複数質問/文字数/状態検証も実行する。

SDKを追加せず、stdlib HTTPS専用transportでTLS検証・固定2endpoint・bounded body・redirect拒否を実装。
自動retryは0。connect/send/readの各段階で同じmonotonic deadlineの残量を設定する。
WorkerはLambda/lease/評価deadlineの残量から保存用10秒を確保し、Provider全体は最大40秒。
認証・JSON検証もこの同じ予算に含め、終了後にも期限を確認する。
DNS解決やOSのスケジューリングをPythonのsocket timeoutだけで厳密に中断できるとは保証しない。
Lambda60秒の外側期限も残り、結果不明は再呼出しせずRecoveryへ引き継ぐ。

Provider開始の永続記録後に1回だけResponses要求を行う。
timeout/network resetで送信成否不明ならOUTCOME_UNKNOWN、既知のrefusal/incomplete/HTTP失敗はfailed。
429のquota/billing、認証、503、不正JSON/schema、output不足を内部の固定分類で区別する。
公開error契約は維持し、ログは分類文字列のみ。API失敗をFake評価へ置換しない。
明示retry_evaluationのみ新Evaluationを作る。設定は既存execution_config.provider_idに
mode/effort/token上限/月間上限を固定し、model_idはgpt-6-lunaを記録する。

## 認証の選定

第一候補はAWS WIF。既存boto3でregional STS GetWebIdentityToken（ES384、300秒、専用audience）を
取得し、OpenAI token exchangeで短命access_tokenへ交換する。期限を検査し、毎回再取得する。
現在のWorkerロールだけで利用可能とは判断していない。AWS outbound federation、Workerとboundaryの
必要権限、OpenAI側issuer/audience・正確なWorker subject mapping・project service accountの設定が必要。
OpenAI側アカウントの設定権限・availabilityは未確認。今回token発行や設定は行わない。
[AWS WIF](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws)、
[token exchange](https://developers.openai.com/api/reference/workload-identity-federation)、
[AWS側前提](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_outbound_getting_started.html)。

代替は明示secret mode＋同Account/東京のSecret ARNだけ。JSON api_keyをメモリで読み、ローテーションは
次回取得へ反映する。Secrets Managerの一般料金例は1secret約$0.40/月＋$0.05/1万取得。
[公式料金](https://aws.amazon.com/secrets-manager/pricing/)参照。Secret/IAM変更と運用上のローテーションが必要。
WIFは長期キー保管を避けられ、新規Secret資源の固定費も不要なため優先する。
WIF利用条件を満たせない場合は方式変更を別途レビューし、無断fallbackしない。
WIF自身の課金条件・無料枠・地域可用性を今回のAPI試験で確認したとは扱わない。

## 呼出し数・料金

OpenAI選択時だけ、既存1テーブルのUSER領域へProviderUsage/月を作る。UTC月、利用者別100回、全体3000回が既定。
Evaluationに予約月を記録し、両counterと同じCAS transactionで更新する。再配送や応答消失で二重予約しない。
認証失敗等でも予約を返却しない保守的な上限。新Evaluationの明示再評価は1回分を消費する。
Fakeはquotaを消費せず、API/IAMの許可範囲は変更しない。新テーブル/Queue/TTL/Scanは不要。
月間recordは残る。将来の限定cleanupは所有者・月・run証跡を監査して別承認する。
全体counterは専用内部owner名で総数だけを保存する。これはAI回数上限であり、AWS費用や全支出の強制上限ではない。
30人×100回なら最大3000予約/月、1質問の最大4評価は4予約となる。
HTTP全体のabuse/大量新Session作成をこのquotaだけで防げたとは扱わない。

Standard/short-context通常入力$0.10、cached入力$0.01、cache writes$0.125、出力$0.50/100万tokens。
[公式料金](https://developers.openai.com/api/docs/pricing)を2026-10-08に確認。
reasoning tokensは出力tokensの内数であり二重計上しない。固定developer指示を先頭に置くがcache hitは仮定しない。

仮定: 入力3000、可視出力400、reasoning800＝出力1200 tokens/評価、cacheなし。実測値ではない。

| 評価/月 | 通常入力 | 可視出力 | reasoning | 合計USD |
|---:|---:|---:|---:|---:|
| 100 | 0.03 | 0.02 | 0.04 | 0.09 |
| 1000 | 0.30 | 0.20 | 0.40 | 0.90 |
| 3000 | 0.90 | 0.60 | 1.20 | 2.70 |
| 10000 | 3.00 | 2.00 | 4.00 | 9.00 |

medium仮定reasoning2000なら出力計2400、1評価$0.0015。100/1000/3000/10000回で$0.15/$1.50/$4.50/$15。
max_output_tokens4096は中断時にも課金を生じ得る。入力6000＋上限出力4096の仮定なら1評価$0.002648。
cache writes premium/税/地域処理premium/為替/無料creditをこれらの例に含めない。
AWS request/log/storage/将来active17Alarmは別料金。実測usageと費用はEval Runnerで集計する。

## Eval・AWS準備・Terraform

`provider_eval.py`は共通事実9fixture＋新スコア境界10fixture、low/medium比較、±1点/状態/latency/usage/費用を集計。
重複・創作・訂正等はmanual annotationのcoverageと率を区別する。未評価はnullでPASSにしない。
label/閾値は実モデル校正前の提案で、既存Formal Performance Gateを変更しない。
liveは明示選択、承認JSONとSHA、calls上限、排他的started journalが必要。今回はoffline corpusだけ実行。

`coaching_live.py`は既存auth_e2e.login/Apiに接続できる再送/owner分離/3ラウンド/retry/stale/履歴とAdmin操作の
suite関数を実装。準備CLIは実要求0。run_with_closureは失敗時にも承認済みClosure callbackを実行する。
実行器へのauth/最新State binding/監査済みClosure callbackの接続は承認後に具体化する。
テストでそのcallbackが失敗時にも呼ばれることは確認するが、実Closure成功と扱わない。
server-only Fake scenarioは明示validation flag＋owner SHA allowlist。回答magic stringやFrontend指定はない。

TerraformはWorker専用worker_ai_environment入力のみ追加、既定{}。平文キーを受け付けず、
API/Admin/DispatcherへProvider設定を渡さない。非empty時だけmanifestに同じ設定を記録し、読戻しで照合。
IAM/boundary/backend/provider/runtime/512MB/Worker60秒/MaximumConcurrency2/4フラグ/17Alarm契約は維持。
resource block追加/削除は0。既定入力ではprovider環境差分0、新資源/replace/destroyの設計なし。
新ZIPへの将来rolloutは4Lambda＋5alias updateが見込まれるが、実S3 version/saved plan未取得なので確定件数ではない。
WIF権限は今回追加しない。既存初回CI入力guardは変更せず、将来のProvider設定は監査済みlocal CLI経路を使う。

store=falseは全保持ゼロの保証ではない。公開前に利用者への外部AI送信案内、不要な個人情報の入力抑制、
abuse monitoring retention/ZDR条件を確認する。[データ管理](https://developers.openai.com/api/docs/guides/your-data)参照。

検証結果・固定commit/Artifact候補/SHA・CI・AWS読戻しは後続の完了報告とprivate証跡へ記録する。
