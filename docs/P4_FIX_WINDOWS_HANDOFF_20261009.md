# P4総合修正 Windows引き継ぎ — 2026-10-09

本書は旧Cost/Log handoffの自己申告test閉鎖・61件固定・旧FILL/料金を置き換える。Cloudは通常Git pushとoffline試験まで。AWS操作・正式Artifact upload・Enablement/Closure・main mergeの許可は含まれない。[総合レポート](P4_TOTAL_FIX_REPORT_20261009.md)、[実AWS受入](P4_FIX_AWS_ACCEPTANCE_20261009.md)も確認する。

## Gitと検証

作業branchは `codex/p4-cost-log-optimization-20261009`、PR #1はDraft維持。開始remoteは `4eac384dc54e5c66f4b5df4157d678c9e8bd05f4`、mainは `b9ec1f7b02374639ff8eb7310e978b5950565757`。Windows固有の未commit変更を破棄せず、新remote HEAD/CIを確認して別worktreeで読む。

```powershell
git status --short
git fetch origin main codex/p4-cost-log-optimization-20261009
git ls-remote origin refs/heads/main refs/heads/codex/p4-cost-log-optimization-20261009
git log --oneline --decorate -8
git worktree list
```

Cloud結果: Backend1315 passed/0 failed/2 skipped/57 deselected、Ruff check/format PASS、Terraform4validate/49mock PASS、Frontend unit265/全回帰654/E2E24、lint/typecheck/production/Storybook/mock build PASS。Python3.14.7、Terraform1.14.9、uv0.12.19、Node24.19.0/system Chromium。正式CIのNode22/uv0.11.8結果と最新HEADは最終レポート/PR checksを照合する。ローカルbrowser一時設定はcommitしない。

## dev自動Closure

61という固定値を使わない。成功済み最新Enablement receiptのState identityから正式アドレス集合を取得し、承認Alarmを引き、4箇所だけ閉鎖属性へ変更した集合を期待afterとする。

- 新source SHA/hash、Provider lock、正式Artifact/VersionId、Lambda version/alias/AI設定を承認に結合し直す。旧承認JSONを新sourceの実行許可として流用しない。
- Beforeはreceipt/S3 VersionId/hash/lineage/serial、Account/Region、manifest、lockなし、namespaceの既存検査を維持。
- saved planは全アドレス・before属性がStateと一致し、4update＋**完全一致した承認Alarm集合**deleteのみ。他resourceとoutputはno-op。
- apply直前に再読取、afterは全baseline属性とmanifestを検査。mappingはDisabledを要求し、AWS更新で自然に変わるlast_modified/last_processing_result/state_transition_reasonのread-only metadataだけを除外。UUID/ARN/scaling等は厳密一致。create/replace/未知destroy/未承認Alarm/欠落は拒否。
- partial failureやreadback mismatch後はread-only診断のみ。State操作、無断再plan/apply、Artifact上書きを行わない。

## test閉鎖の順序と必要な証跡

1. 新監視仕様へ移行する場合は、閉鎖と混ぜずに別承認planで移行し、39 Alarmをreadbackする。
2. 39 Alarmを保持したまま4入口を閉じ、外部Invoke/直接DDB writerも停止したことを独立に確認する。concurrencyは既存unreserved=-1、Worker mapping MaximumConcurrency=2を変更しない。
3. 最後のwriter停止時刻から各aliasの`MaximumEventAgeInSeconds + Timeout`を待つ。async設定がない場合はデフォルト6時間＋timeout。SQS遅延・inflight、Recovery将来due、DLQ、未解決OutcomeUnknownを処理・照合する。API/mapping/scheduleの4falseだけを「残務なし」と呼ばない。
4. 観測CLIはStateを固定Versionで読んでbefore/after一致を検査するが、出力は`TEST_DRAIN_OBSERVED`, `closure_eligible=false`。SQS概算/GSIの限界を示す。これを自動でapproved/confirmedへ変換するコードはない。
5. 独立reviewerがprivateなwriter-control、全送受信queue ledger、incident解決記録を審査し、State-bound承認を作る。残務ゼロを証明できないなら39 Alarmを維持する。
6. Terraformには承認ファイルpath＋**実bytesのSHA256**を渡す。booleanだけではplanが拒否される。saved planのhashと清潔なcommitted source SHAを別に承認し、guarded preflight/applyを使用する。
7. apply前の再照合、39 deleteのみ、readback0とbaseline不変を検査。attempt記録後の再applyは禁止。証跡は発行から最大900秒で、長い調査・plan承認待ちの後は観測と承認を取り直す。

AWS受入時のみ、Account/Region/profile/既存権限とread許可を確認して `P4_AWS_EXECUTION_READY=true` を設定する。下記はCloudで実行していない。write許可はsaved planごとに別途確認する。

```powershell
Set-Location backend
uv run --locked python skills/p4/test_monitoring_closure.py --manifest <private-test-manifest.json> --account <承認Account> --region ap-northeast-1 --output <backend/.p4-artifacts/新規観測.json>
# この出力だけでは削除承認にならない。
```

承認proofの必須要素（実値はprivateのみ）:

| フィールド | 条件 |
| --- | --- |
| status/alarm_count | `APPROVED_TEST_DRAIN` / 39 |
| account_id/region/run_id | 現在の専用test manifestと完全一致 |
| manifest_sha256 | sorted keys/compact JSONのSHA256 |
| state_identity | lineage/serial/VersionId/State raw bytes hashを実S3読取から固定 |
| issued_at_epoch/expires_at_epoch | 整数、現在を含み最大900秒 |
| issued_at/expires_at | 同じepochのtimezone付きRFC3339。Terraform plan/applyでも期限検査 |
| approved_by/observed_by | 両方非空・異なる独立担当者 |
| writers_stopped_at_epoch | 最後の全writer停止時刻。async lifetime+timeoutを満たす |
| reviewed_evidence | `external_writers`, `queue_ledger`, `incident_resolution`ごとのprivate path/bytes SHA256 |
| reviewed資料 | 同じAccount/Region/run/manifest/State、status RECONCILED、整数remaining=0、観測はproof発行前60秒以内 |
| resolved_outcome_unknown | incident資料と一致するowner/evaluation_idの正確な集合。未解決recordがあれば閉鎖拒否 |

Table base Scanは全ページ`ConsistentRead=true`、GSIだけを根拠にしない。既存CI test roleにScan/GetFunctionEventInvokeConfig等がない場合は自動閉鎖不可。適切な既存read roleを確認し、IAM boundary/WIFを無断緩和しない。証跡の文面だけで外部writer停止やqueue ledger照合を捏造しない。

test tfvars追加項目:

```text
test_monitoring_enabled=false
test_closure_confirmed=true
test_closure_evidence_path=<承認proofのprivate絶対path>
test_closure_evidence_sha256=<承認proof実bytes SHA256>
api_enabled/worker_enabled/streams_enabled/scheduler_enabled=false
```

saved planを新規privateディレクトリへ作成・hash確定後、次のformal guardを使う。出力/plan/承認/State本文をGitHub artifactや通常ログへ公開しない。

```powershell
# root/.p4-artifacts配下の新規run directoryを使う。manifest/proof/planもprivate path。
uv run --locked python skills/p4/test_closure_apply.py preflight --manifest <private-manifest> --account <承認Account> --region ap-northeast-1 --directory <private-run-dir> --plan <承認saved-plan> --plan-hash <承認SHA256> --proof <独立承認proof> --proof-hash <承認SHA256> --source-sha <承認commit SHA>
# preflightが成功してもwrite承認は別。承認後のみ同じ引数でapplyを1回。
uv run --locked python skills/p4/test_closure_apply.py apply --manifest <private-manifest> --account <承認Account> --region ap-northeast-1 --directory <private-run-dir> --plan <承認saved-plan> --plan-hash <承認SHA256> --proof <独立承認proof> --proof-hash <承認SHA256> --source-sha <承認commit SHA>
```

saved plan以外をapplyしない。repo source・Terraform1.14.9・canonical test backend/workspaceを確認する。個別attemptとproof hashに対する共通attemptをcreate-only記録し、別directoryへ移して同じproofを再利用することも禁止する。失敗時は手動State操作をしない。

## test再開

monitoring=true、confirmed=false、proof path/hashをクリアし、**4入口falseのまま39 Alarmを復元**する別承認planを使用する。復元後のmanifestで次をread-only実行し、成功後に別enablement planを承認する。

```powershell
uv run --locked python skills/p4/test_reopen_preflight.py --manifest <private-restored-test-manifest> --account <承認Account> --region ap-northeast-1
```

API、Worker/Streams mapping、Schedulerの依存関係も全39 test Alarmの作成を先行させる。SNS subscriptionの到達確認と実Alarm属性readbackを省かない。

## customer14→developer3の短縮

`log_usage`だけを変更して直接applyしない。正式runnerはStateの用途と実planの5groupを監査する。保持増加/14日継続/初回createは短縮承認不要。既存groupのreplace/destroy/rename/address変更は拒否する。

- `P4_LOG_RETENTION_APPROVAL_PATH` / `P4_LOG_RETENTION_APPROVAL_SHA256`でprivate承認を指定。
- 承認operationは`LOG_RETENTION_SHORTENING`。現在のAccount/Region/run/manifest hash/State identity、発行/期限（最大24h）、独立approved_by/reviewed_by、全shorteningのaddress/name/before_days/after_daysを固定する。
- `impact_reviews`にはincidents/support/auditの3資料path/hash。各資料は同じcontext、domain、`PRESERVED_OR_NO_OPEN_ITEMS`、整数open_items。未解決件数>0なら`preserved_artifacts`のprivate path/hash一覧が必要。export本文のhashも照合する。
- plan bindingにStateと承認hashを保存し、apply直前に同じStateと全資料を再検査する。資料欠落/改変/期限切れなら短縮しない。
- 現GitHub workflowは私有保全資料の自動輸送を追加していない。正式runnerへ資料を配置・環境設定する運用が未了なら短縮はFail Closed。一般公開workflow入力へState本文や保全ログを貼らない。customer14を維持して作業を止める。

## 90日以上の本人問い合わせ

本人の認証subject、または退会後のreviewed support ticketで本人を確認する。正確なowner/evaluation_idを取得し、既存tableの `USER#{owner}` / `EVALUATION#{id}` をConsistentRead exact GetItem。問い合わせ用にScan、履歴write、新テーブルを作らない。原Itemには回答/採点が含まれるためbackend/.p4-artifacts内のprivate端末でだけ扱う。

本人確認資料はstatus=`IDENTITY_VERIFIED`、owner/evaluation_id一致、verification_method=`authenticated_subject`または`reviewed_support_ticket`、verified_by非空、issued/expires epochが現在を含む900秒以内。資料の実SHAを別に固定する。

```powershell
uv run --locked python skills/p4/support_history.py --record <backend/.p4-artifacts/private-GetItem.json> --owner <本人owner> --evaluation-id <UUID> --identity-proof <private本人確認.json> --identity-proof-sha256 <承認実SHA256> --output <backend/.p4-artifacts/新規summary.json>
```

古い合法schemaや失敗評価をdecodeし、provider不明はunknown。別人/別evaluation/期限切れ/欠落は拒否。Cognito退会を理由に認証を緩和せず、DDB item削除後はunavailableと報告する。回答全文/採点本文/secretを通常ログへ出さない。PITRは現在無効、90日保存と35日復旧を区別して別途方針承認する。

## 最終受入の停止条件

Worker/Dispatcher両系列の実CloudWatch/SNS、test drain/State照合、90日実データ、PITR/削除運用を確認する。cold p95=2003.466msの2000ms超過FAILと実AI30人同時未検証を解消するまで公開受入PASSとしない。AWS操作の可否はその場の明示許可を確認する。
