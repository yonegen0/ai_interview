# P4総合修正レポート — 2026-10-09

8指摘のコード修正とオフライン検証を実施。AWS実機受入は未完了であり、公開運用準備完了とは判定しない。AWS SDK実接続、Terraform実apply/destroy、正式S3 Artifact upload、Enablement/Closure実行、実AI呼出し、main merge、force pushは実施していない。

## Git・調査範囲

- repository: `yonegen0/ai_interview`、作業branch: `codex/p4-cost-log-optimization-20261009`、[PR #1](https://github.com/yonegen0/ai_interview/pull/1) は開始時open/Draft。
- 開始時およびpush準備前のremote branch: `4eac384dc54e5c66f4b5df4157d678c9e8bd05f4`。remote main: `b9ec1f7b02374639ff8eb7310e978b5950565757`。引継ぎSHAを無条件に最新とは扱わず、fetch/ls-remote/PR情報を照合した。
- 元の `/workspace/ai_interview` はcleanな `work` branch/mainと同じHEAD。専用worktree `/workspace/ai_interview-p4-fixes` を作成し、元の変更を破棄していない。
- AGENTS.md、Cost/Log plan、CSV/JSON、Windows handoff、Terraform runbookを確認。
- `/workspace/ai_interview-backend-review-20261009.md` は存在し、全文と69 Pythonファイル個別評価・問題JSON評価を確認。8項目の範囲外で追加修正が必要な実害のある指摘は見つからなかった。
- 最終HEAD/通常push/remote一致/最新GitHub CIは、最終回答およびPRの最新checksと照合する。本文のcommit自身のSHAは `git log -1 --format=%H -- docs/P4_TOTAL_FIX_REPORT_20261009.md` で取得できる。

## 8項目の修正・検証

| 項目 | 修正前の問題・根本原因 | 修正ファイル | 修正内容・追加試験 | 判定 |
| --- | --- | --- | --- | --- |
| High 1 Closure | before=61+Alarm、after=61の固定数。資源集合の承認範囲と固定インフラ構成を混同 | `closure_adapter.py`, `test_closure_inventory.py`, 既存Closure fixture | 正式Stateをアドレス→全属性へ展開し、承認Alarm集合との完全一致、既存4updateだけを導出。before全planとState属性一致、apply直前の同一State、after全baseline属性を照合。2つのmappingのstateはDisabledを要求し、last_modified/last_processing_result/state_transition_reasonという3つのread-only観測metadataだけをafter照合から除外。UUID/ARN/scaling/他属性は厳密不変。旧61、新72/76の合成構成、Alarm1/17/21、追加・欠落・未承認削除・replace・State不一致・成功・途中失敗・readback不一致を試験 | offline PASS。実Closure未実行 |
| High 2 test閉鎖 | confirmed=trueだけで削除可能。概算SQSとGSIの0を完全drainと混同し、State/鮮度/将来残務の結合がない | `test_monitoring_closure.py`, `test_closure_guard.py`, `test_closure_apply.py`, `test_reopen_preflight.py`, `deployment_guards.py`, test/service変数・outputs・runtime・auth、`test_deployment_guards.py`, `test_state_snapshot_guards.py` | 観測はeligible=falseのまま。独立承認済みのwriter停止・queue ledger・incident解決資料をprivate hashで固定。Account/Region/run/manifest/lineage/serial/VersionId/State hash一致と15分TTL。全aliasのasync lifetime+timeout経過、強整合base-table全ページ、未来Dispatch/processing/未解決OutcomeUnknown、SQS visible/inflight/delayedと両DLQを検査。plan/preapplyのState/期限/ファイル再確認、39 Alarm以外の変更拒否、attempt後再apply禁止。再開39readbackと全入口の依存順序 | offline PASS、AWS受入未検証。必要なread権限・外部writer停止を実証できなければ停止 |
| Medium 1 管理証跡 | 管理保存はQuestionBankChangeなのにIdempotencyRecordを取得 | `runtime_receipts.py`, `test_validation_contract_fixes.py`, transport fixture | `PK=SYSTEM#QUESTION_BANK`, `SK=OP#{admin}#{request_key}`を強整合exact GetItem。実decoderでschema/物理key/owner/UUID/reply200を検証。成功したadd/edit/delete/reorderと対応する記録だけを採用。欠落はnot_run、不正はfailed。正常・欠落・owner/key/schema/応答不正・失敗runを実Backend保存レコードで試験 | offline PASS。ConditionCheck直接観測はnot_runを維持 |
| Medium 2 Auth E2E | 1問でも無条件に2問目200を要求。固定careerカテゴリにも依存 | `auth_e2e.py`, `test_validation_contract_fixes.py` | Practice optionsとSessionResponse契約を検査し、通常はfull session。hasNext=trueならquestionNumber2の200、falseなら409 SESSION_COMPLETED。カテゴリに問題がない場合は409 CATEGORY_UNAVAILABLE。同一要求replayと改変要求409を検証。1/2/3問、カテゴリなし、誤った200/500を実Backendで試験 | offline PASS。Cognito/JWT/本人分離の実AWS E2E未実行 |
| Medium 3 OutcomeUnknown | 発行済みWorker系列がDispatcherだけのAlarmに含まれない | `manifest_alarms.py`, `manifest.py`, `monitoring.tf`, `outputs.tf`, `test_alarm_delivery.py`, cost/mock tests | 既存名/address/SNSを保ち、Worker+DispatcherをSUM([wo,do])、60秒1-of-5へ集約。Worker発行経路を実Worker＋mock provider失敗で確認。両系列/片側/無通信/遅配/回復をモデル試験。既存schema2/3とmarkerのないschema4は旧readbackを維持 | offline PASS、CloudWatch/SNS未検証 |
| Medium 4 EvaluationFailed | FILL最新0＋60秒1-of-1が遅配でOK固定になり得る | `monitoring.tf`, `manifest_alarms.py`, `test_alarm_delivery.py`, Terraform cost_logs mock | FILLを除去しSUM([wf,df])、60秒1-of-5、>=1、missing notBreaching。単発失敗を維持し4分程度の遅配余裕を確保。同じ潜在問題があるtest failure-rateもFILLを外し900秒1-of-3、最低10件条件を維持。旧FILLの取りこぼしを限定モデルで再現し、producer/契約/遅配/欠測/回復を試験 | offline PASS。実CloudWatchの時刻評価は未検証 |
| Medium 5 90日履歴 | 旧120日試験は時計を進めず日時の足し算だけ。private snapshot CLIの本人確認・取得失敗境界も不足 | runtime/skillsの`support_history.py`, `test_support_retention.py`, `test_operational_logs.py` | exact USER/EVALUATIONキーとConsistentReadの既存DDB読取を追加。時計を91/120/365日進め、既存schema1のconfigなし終端失敗、通常completed、OUTCOME_UNKNOWN failedを復元。本人確認資料hash/15分期限/owner/evaluation照合、private入力・出力600、欠落拒否。削除済みitemを捏造せずunavailable。新履歴・新table・TTL・本番書込なし | offline PASS。実90日データ/退会運用/PITR未検証 |
| Medium 6 保持短縮 | developer選択だけでcustomer14→3を承認なしに実行可能 | `deployment_guards.py`, `terraform_dev.py`, `test_deployment_guards.py`, runbook/handoff | 用途の旧State照合と5groupのplan監査。customer→developer、14→3その他の短縮はState/manifestに結合した明示承認が必要。障害/support/auditのレビュー、未解決案件のprivate保全資料hashを検証。replace/destroy/rename/住所変更を拒否。apply直前も同じState・承認・証跡を再検査しplan bindingに固定 | offline PASS、実plan/保全運用未検証 |

`backend/skills/p4/` と `backend/tests/unit/` を上表の短いpathの基準とする。変更一覧は `git diff --name-only 4eac384dc54e5c66f4b5df4157d678c9e8bd05f4 HEAD` でも確認できる。

## 再現と試験結果

修正前にClosure回帰15ケースのうち7 failure、管理/Auth回帰13 failure、監視回帰14ケースのうち10 failureを確認した。残りは旧実装の自己申告guard/不足試験を実コードから確認し、新境界をmockで検証した。AWS実StateやCloudWatchの再現は実施禁止のため未実行。件数・閾値を削って合格にはしていない。旧Terraform「自己申告だけで閉鎖成功」のケースは、本来の安全契約に従って「拒否」を検証するケースへ変更し、ケース数を維持した。

| 対象 | 結果 |
| --- | --- |
| 修正前Backend全offline | 1200 passed / 0 failed / 2 skipped / 57 deselected |
| 修正後Backend全offline | **1315 passed / 0 failed / 2 skipped / 57 deselected**。socket/boto3 HTTP禁止fixture有効 |
| Ruff check / format check | PASS。Python3.14対象・既存rule/line-length維持 |
| Terraform fmt | PASS |
| 隔離Terraform validate | bootstrap/dev/test/service **4成功**。backend initなし、AWS認証/metadata無効 |
| 隔離Terraform mock | service47 + bootstrap2 = **49 passed / 0 failed**。入口のAlarm依存追加後にservice47と依存root validateも再実行 |
| manifest schema2/3/4 | 既存全offlineと新legacy/migration/metric-reference試験でPASS |
| Closure / State / Alarm / ログ / 履歴 | 上記全offline内でPASS。限定AlarmモデルはAWS実機受入ではない |
| interview-demo | PASS、local memory/Fake Providerのみ |
| Frontend unit / lint / typecheck | unit **265 passed**、lint/型検査PASS |
| Frontend browser全回帰 | **654 passed**。Node24.19.0/system Chromium、一時設定で実行、製品設定は未変更 |
| Frontend build/Storybook/mock/E2E | **production/Storybook/mock build PASS、E2E24 passed/0 failed** |
| Lambda ZIP static | **PASS**。固定production Wheel、CPython3.14/Linux x86_64、2回buildのZIP hash一致、展開先から4handler import/15問asset読取成功。socket接続禁止。正式Artifact未操作 |
| Git diff --check / 秘密情報監査 | PASS。State本文/private evidence/認証情報を追加しない。検査で秘密値を出力しない |
| GitHub正式CI | 通常push後に最新HEADを確認。実行結果は成果物確定記録および最終回答を参照 |

ローカル環境はPython3.14.7、uv0.12.19、Terraform1.14.9、Node24.19.0。GitHub CI固定版はuv0.11.8/Node22。Providerは既存lockのbootstrap/test/service6.64.0、dev6.65.0を変更していない。sandbox内のProvider IPCとFrontend子プロセスが制限された初回起動失敗は、AWS認証を除いた隔離実行/ローカル接続可能な環境で再実行して解消。browserの共有依存symlinkによる初回配信失敗もworktree内コピーで解消した。

## 監視案の比較と時間特性

| 案 | 単発/遅配/正常欠測 | 資源・料金 | 判断 |
| --- | --- | --- | --- |
| FILL＋1-of-1 | 最新0が合成され、過去の遅配単発を見落とすモデルを再現 | 現行 | 不採用 |
| FILLなし＋1-of-1 | 合成最新0を除くが最新期間だけの評価は遅配余裕が小さい | 同参照数 | 不採用 |
| FILL＋M-of-N | AWS公式の回避案。M=2以上は単発を失うため不可。1-of-5なら改善するが合成0が残る | 同参照数 | 比較のみ |
| **FILLなしSUM＋1-of-5** | Worker/Dispatcherどちらの1件もbreach。missing notBreachingで無通信を正常扱い | 同じ既存Alarm/2参照 | 採用 |
| Role別Alarm2件 | 役割別だがAlarm資源が増え、既存名前・readback・通知運用を増やす | 2参照の課金は同様だがAlarm数増 | 不採用 |

[AWS metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)のFILL警告とarray SUMを確認。scalar SUM(single series)を使っていない。60秒periodは維持し、>=1を1/5で判定するため「5回の失敗」を待たない。限定モデルではtimestampが評価範囲に残る約4分の遅配を検出できる。周期境界60秒＋遅配4分＋次回評価60秒を仮定した保守的検知予算は**最大約6分**。CloudWatch配送・評価・SNSの上限保証ではなく、5分を超える遅配の確実な検出を主張しない。CloudWatchは追加datapointを取得するため、実際の復帰時間も実機で確認する。1/3×900秒のtest failure-rateは45分窓で、遅配の余裕と通知継続時間が増える。新metric名/高cardinality dimension/閾値緩和なし。

## Alarm数・メトリクス参照・料金

720時間モデルの仮定単価$0.10/metric-reference/月を維持。Math expression自体を追加課金の指標として数えず、入力MetricStatを数える。OutcomeUnknownに既存Worker系列1参照を追加し、新Alarmは増やさない。過去Bモデルは比較基準として変更しない。CSV/JSONの全64行（cost48/sensitivity16）を一致更新した。Tokyo最新SKU、無料枠残量、実請求は未取得。

| 構成 | Alarm数 | 修正前→後の参照 | 720h gross Alarm費 |
| --- | ---: | ---: | ---: |
| developer dev | 17 | 17→18 | $1.80 |
| customer dev | 21 | 22→23 | $2.30 |
| test稼働 | 39 | 42→43 | $4.30、24hなら$0.143333 |
| 検証済み閉鎖 | 0 | 0 | $0 |

30ユーザー/customerの全AWSモデルは、無料枠消費済み **$5.710973/月**、仮定無料枠あり **$1.724023/月**。旧Bとの差は約+$0.602665 / +$0.600000。今回追加分はdev月+$0.10、test24h+$0.003333、併存+$0.103333。M-of-Nの期間変更は参照数・Alarm料金を増やさない。customer追加4Alarmの5参照差（対developer）は従来どおり+$0.50/月。実残存時間に対するtest節約は `43 × 0.10 × 安全に削減できた時間 / 実月時間`。無料枠10参照はAccount共有、二重控除しない。10月の実月時間744を正式請求では使い、720hモデルを請求額と扱わない。

## 既存機能とTerraform差分予測

- dev Closureは正常Enablement後の条件付き自動実行を維持。資源数変更だけでは止めず、正式State identityと承認済みAlarm集合が成立するときだけ進む。4update以外の変更、未承認削除、create/replace、未知属性、State不一致、partial failure後の再applyは拒否。
- schema2/3と旧schema4 readbackは旧指標契約のまま。新schema4に`monitoring_contract_version=2`とproof digest metadataを出力。過去receiptを新監視定義で勝手にPASSにはしない。新配備後のenablement/validation承認は変更後source/manifest/hashで取り直す。
- 稼働customer devならOutcomeUnknown/EvaluationFailedの既存Alarm2updateを予測。developerならOutcomeUnknown1update。testならOutcomeUnknown/failure-rate2update。名前/address/SNSは同じで、既存17削除なし。
- test閉鎖は39承認Alarm deleteのみ、非Alarmは属性を含めno-op。モニタリング仕様移行や保持変更を同じ閉鎖planへ混ぜない。再開は39create→closed入口readback→enablement、全入口にtest Alarm依存を追加。
- 保持日数変更は既存5groupのretention属性だけのupdateを予測。Python監査はreplace/destroy/name/address変更を拒否。実AWS planは未取得なので、ドリフトやProviderの実差分をPASSとはしていない。
- Worker MaximumConcurrency=2、Scheduler毎分、SQS retry/DLQ、DDB PAY_PER_REQUEST、Cognito/JWT/IAM boundary/WIF、Provider、既存Artifactを変更していない。回答/採点/処理レコードのTTL、新table、履歴write、State削除・再作成なし。
- Frontend製品コード/API契約は変更なし。support exact読取helperだけがruntime source変更に含まれ、将来の新Artifact静的検証は必要。既存Artifactの上書きは禁止。

## 90日履歴とPITR評価

Evaluation保存はcodec schema1＋owner別既存キー。期限は処理deadlineであり保持TTLではない。91/120/365日後も保存済みitemを読める。completedはexecution_config/leaseが必要な現契約を維持し、不正な「completedなのにconfigなし」を新たに許容していない。旧configなしの合法なPREPARATION_FAILED終端レコードはprovider/model unknownとする。OUTCOME_UNKNOWN failedも採点を捏造せず失敗分類だけを返す。

Cognito退会/無効化は認証許可を戻す理由にならない。既存コードに包括的な退会データ消去APIはなく、Cognito削除とDDB item削除は別。退会した本人からの問い合わせはreviewed support ticketによる独立本人確認が必要。管理者がDDB itemを削除済みなら取得不可と報告し、ログや計算から回答/採点を復元しない。実データ・削除方針は未受入。

現行PITR無効は維持。[AWS PITR仕様](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html)では保持1～35日、default35日、期間を短くしてもテーブル/LSIサイズに基づく費用は下がらない。90日問い合わせデータの存続と、削除/誤更新からの35日復旧を区別する。追加月費は `テーブル＋LSI実GB × Tokyo PITR単価`、復旧時は復旧GB課金と復旧先storage等が別。例として仮定$0.20/GB月なら1GBで$0.20、10GBで$2.00だが、Tokyo実単価確認済みとはしない。

PITRは元State/tableを上書きせず新tableへの復旧となるため、今回の「新tableなし」作業では復旧実行もしない。誤削除/論理破損への効果、LatestRestorableDateTimeの約5分遅れを踏まえたRPO、データ量依存RTO、削除済み本人データを再公開しない手順、費用上限をWindowsで別途承認する。長期履歴90日をPITRだけで保証できるとはしない。

## AWS/Windows残課題

[Windows修正引継ぎ](P4_FIX_WINDOWS_HANDOFF_20261009.md)と[AWS受入チェックリスト](P4_FIX_AWS_ACCEPTANCE_20261009.md)を使用する。

1. State/lock/Account/Region/Artifact/aliasの正式読戻しと新source/hash承認。Cloudにはcredentialsがなく、AWSは一切呼んでいない。
2. test base-table ScanとGetFunctionEventInvokeConfig等の既存read権限、外部writer停止/queue ledgerの実証。CI test roleの既存query権限だけではScanできない可能性があり、権限を無断拡張しない。証拠/権限不足なら39 Alarm維持。
3. Log短縮のprivate承認・incident/support/audit保全資料を正式runnerへ安全に渡す。既存GitHub workflowにはこれらを自動輸送する仕組みを追加していないため、資料配置/環境設定未了のrunnerでは短縮が拒否される。通常のcustomer14継続配備は影響なし。
4. Worker/Dispatcher単独・同時・欠測・遅配・復帰のCloudWatch実評価とSNS到達。単発>=1が検知されなければ受入FAIL。
5. test39 delete/readback0・再開39readback・期限切れ/State変更/途中失敗停止の実環境演習。概算0/GSI0だけのapproval禁止。
6. 90日以上の実DDBデータ存続、退会/管理者削除と本人確認、PITR/RPO/RTO/費用方針を決定。
7. cold-start p95 **2003.466ms > 2000msはFAIL継続**。実AI30人同時性能も未検証。今回の修正で公開可能とは判断しない。

## 成果物確定記録

- Closure実装commit: `e37c337`。
- 残7項目・費用整合実装commit / 静的候補ZIP source: `13c3d41fd7350d988131a594ca865ca174fcb38e`。
- Backend最終全offline: 1315 passed/0 failed/2 skipped/57 deselected（mapping metadata/identity4拒否を追加後）。
- Frontend production/Storybook/mock build成功、E2E24 passed/0 failed。一時browser設定を削除し、製品tracked差分なし。
- Lambda候補ZIP19,044,650bytes、固定依存で2回hash一致。runtime/asset importはsocket禁止で成功。候補はCloud tempのみ、正式S3/既存Artifact未変更。
- Terraform Provider lock/State/Artifactのtracked変更なし。4validate/49mock、fmt、Ruff、diff --check、秘密情報監査成功。
- 正式GitHub CIは通常push後に確認し、その観測結果を本節へ追記する。未実行/未完了をPASSと扱わない。
