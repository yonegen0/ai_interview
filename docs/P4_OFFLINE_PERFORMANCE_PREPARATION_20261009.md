# P4 offline性能分析・30人負荷試験準備 — 2026-10-09

PR #1のmerge監査から独立した分析branch。製品Python、依存lock、Lambda memory、Worker concurrency、Scheduler、性能Gateは変更しない。正式cold-start p95は **2003.466ms > 2000ms、FAIL継続**。本書のローカル値はAWS Gateを更新しない。

## cold-start分析

初期化はaws_runtime import → AwsSettings検証 → SDK client → repository → role-specific handlerという構成で、build_entryはlru_cacheによりwarmで再利用する。15問JSONはAPI/Admin初回compositionで検証される。Worker Provider選択は明示設定のみで、API/Admin/Dispatcherに実AI clientを作らない。

socket禁止のWindows import profile1回ではaws_runtime累積523.5ms、boto3累積241.8ms。SDK/依存importが支配的だった。これはLambda Init Durationではない。初回SDK client construction、credential discovery、network latencyは下の比較測定から除外した。

Worker/Dispatcher importをrole branchへ移す候補を実装し、同一Python/依存でbaselineとcandidateを交互にfresh processで比較した。API compositionまで測り、認証不備401が維持されることを確認した。

| ローカルcombined proxy | baseline median/p95 ms | candidate median/p95 ms |
| --- | ---: | ---: |
| Windows Python3.14.4、各20回 | 435.71 / 618.07 | 466.99 / 597.93 |
| WSL Linux x86_64 Python3.14.4、各30回 | 1027.17 / 1190.05 | 1046.08 / 1208.71 |

改善を断定できず、候補は**採用しなかった**。製品コードを元のGit内容へ戻し、候補bytes/hashと測定結果をprivateに保管した。WSLはWindows mount上のsourceを使うため、そのI/O時間をAWSへ外挿しない。API以外へ遅延importの費用を移すだけの案や、SDKを後回しにしてInitだけ短く見せる案も正式cold性能改善とは扱わない。

残した `backend/skills/p4/cold_start_benchmark.py` はcredential/envを除外し、socket禁止、SDK factory stubの下でfresh-process import/composition/401を比較する。成功business request、AWS SDK初回処理、Lambda CPU/ネットワークを測るものではない。

```powershell
# backendから。未使用のprivate出力pathを指定する。
python skills/p4/cold_start_benchmark.py --baseline <baseline-worktree> --candidate <candidate-worktree> --rounds 20 --output <private-new-result.json>
```

メモリは512MBを維持。[AWS memory仕様](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html)ではCPUもmemoryに比例し、1769MBで1vCPU相当。512→768MBはbilled durationが2/3以下、512→1024MBは1/2以下にならないとGB-secondの単純費用は減らない。network支配ならその短縮は保証できない。別承認のAWS実測でInit/Duration/total API cold latencyと費用を分けて比較する。無断memory変更・ARM化・Provisioned Concurrency導入はしない。

## Fake Providerによる30人受付

`backend/skills/p4/concurrency_probe.py` を追加した。MemoryRepository、既存HTTP handler、Coaching V2初回回答、FakeProvider、Dispatcher、Workerを使用する。30人のsession/question準備後、Barrierで回答POSTを同時開始し、Worker threadを**2**に固定してevaluation/feedbackを読む。結果JSONへ回答/採点本文・tokenを保存しない。CLIはsocket/SDK clientを禁止し、live接続モードを持たない。

実測: **30受付 / 30完了 / feedback30成功 / failed0 / 未観測0 / Provider呼出30 / peak concurrency2**。Fake delay20ms、local poll50msで全結果観測2.426秒、API proxy p95 62.67ms。Memoryのglobal lock、同一process、SDK/Gateway/SQS不在なので、実AI30人や正式API p95のPASSではない。

```powershell
python skills/p4/concurrency_probe.py --participants 30 --provider-delay 0.02 --output <private-new-fake-result.json>
```

### Worker2の待ち行列下限

30件集中時は15波。delivery/init/storage/network/retry/pollを無視した楽観下限:

| 1件処理秒（仮定） | 最後のterminal下限秒 | 安定throughput上限/分 |
| ---: | ---: | ---: |
| 0.5 | 7.5 | 240 |
| 1 | 15 | 120 |
| 2 | 30 | 60 |
| 5 | 75 | 24 |
| 20 | 300 | 6 |
| 40 | 600 | 3 |

全結果30秒Gateには**処理2秒未満＋残りoverheadの余裕**が必要。20秒Providerなら300秒以上となり、利用者が待てるという限定的な実用性と正式Gateを区別する。Provider deadline40秒・Lambda60秒・十分な残時間を要求するWorkerを維持。送信後不明のProviderを再呼出して料金を増やさず、OutcomeUnknown/lease/deadline/recoveryの既存回帰を再利用する。retry・DLQ・Recovery実AWS効果は未受入。

### 実API試験用の準備

`campaign(clients, timeout=30, poll_seconds=2)` は既存 `auth_e2e.Api` と同じcall interfaceを持つ。承認済みrunnerから合成ユーザーのclient30件を渡すことで、同一HTTPシーケンスを使える。prepared sessionsから同時回答受付、既存キーによるPOST各1回、GET poll、feedback、status/latency集計を行う。POST retryはしない。現時点ではlive CLI/自動ログイン/enablement/cleanupを実装していない。

将来のlive手順は次の順で、別承認後に実施する:

1. source/main/CI、Account/Region、専用test manifest/最新State、4flags/39 Alarm、Worker2、SNS購読、Provider設定を照合。devを試験のため再開しない。
2. test Roleのread権限とcanonical State/lock write scopeを別承認で整備し、独立drain/再開ガードを維持。
3. 合成30identityをallowlist化し、Cognito/JWTを既存手順で取得。tokenはprivateメモリのみ。実利用者を試験に使わない。
4. 実AIの場合はmodel/effort/max_output/最大30 Provider callと費用上限を個別承認。session準備もAWS writeとして承認に含める。token count/limitは既存eval_budget経路を用い、認証/料金確認のための外部APIも未承認で呼ばない。
5. API2秒・全結果30秒の既存Gateを固定し、既定2秒pollでcampaignを実行。429/5xx/Timeoutは集計し、失敗を成功として再送しない。SDK、DDB、SQS、Backlog/DLQ、cold/warm、Recovery、Provider usageを既存private証跡経路で観測する。
6. 不明・残務を解決し、独立test閉鎖証跡の承認工程へ進む。キューpurge/ユーザーItem削除で成功を作らない。dev Enablementを別途行う場合はAGENTSの条件付きClosureに従う。

## OpenAI費用・制限

[OpenAI Docsのgpt-6-lunaページ](https://developers.openai.com/api/docs/models/gpt-6-luna)を今回再取得した。Standardのshort context、cacheなし入力$0.10/1M、出力$0.50/1M。入力3000・出力1200（reasoningを含む）の仮定で1評価$0.0009、30件$0.027、600件/月$0.54。入力6000・出力上限4096なら30件$0.07944、600件$1.5888。token実測・別認証料金・地域premium・retry/不明送信を含む保証値ではない。AWS費用とは別に管理する。

[Rate limits公式資料](https://developers.openai.com/api/docs/guides/rate-limits)のBuild/Launch/Growや公開model上限は、対象projectの実RPM/TPM・残予算の証明ではない。Worker2でも2秒処理なら60評価/分にtoken量が加わる。実project limits/レスポンスheaders/残予算を承認時に確認する。WIF/trust、effort、Provider選択、アプリ内月上限100/user・3000/globalは変更していない。

## 検証と未完了

Backend全offline **1322 passed / 57 deselected**（既存1317＋新5）、Ruff check/format PASS。回帰はsocket/SDK禁止fixture下で実行。新試験はcredential隔離、fresh-process composition/401、2lane HTTP campaign、待ち行列下限、参加人数制限を検証する。Frontend/製品Python/依存/TF差分はないため、元P4 SHAの既存CI・Artifact証跡を再利用する。

CloudWatch/SNS、test閉鎖/再開、Cognito/JWT、90日実保存、PITR/削除運用、正式cold Gate、実AI30人は未受入。分析branchをmergeしてもAWSの性能改善や公開準備完了は意味しない。
