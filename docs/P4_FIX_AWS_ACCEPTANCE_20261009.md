# P4修正 AWS実機受入チェックリスト — 全項目未実行

Cloudは本チェックリストのAWS API/plan/apply/送信試験を実施していない。各試験のprivate証跡・担当者・時刻・対象Stateを保存する。別の明示承認を得てWindowsから実施し、実ユーザーデータを試験対象にしない。[操作手順](P4_FIX_WINDOWS_HANDOFF_20261009.md)と[offline結果](P4_TOTAL_FIX_REPORT_20261009.md)を参照。

## 読取り・配備前

- [ ] 最新remote HEAD、main、Draft PR #1、最新GitHub CIを照合。未commit変更を保護。
- [ ] Account/Region、canonical bucket/key/default workspace、lineage/serial/S3 VersionId/hashを固定し、lockなし・同prefix State外資源なしを確認。
- [ ] 既存Artifactのversion/hash、Lambda version/alias、AI Provider、Cognito/JWT、IAM boundary/WIFを実readback。旧Artifactを上書きしない。
- [ ] 新schema4 marker2へ変更する正式planを監査。schema2/3/旧4の過去receiptはそのまま歴史証跡として保管。
- [ ] 保持変更は5group同名/addressのretention updateのみ、create/replace/destroyを混ぜない。
- [ ] 14→3その他shorteningは、State-bound private明示承認とincidents/support/audit保全資料hashが揃っている。無ければ14日を維持。
- [ ] formal runnerへ私有資料を安全に配置できることを確認。public workflow入力/通常ログ/commitへStateや資料本文を出さない。
- [ ] Terraform実planは未受入であり、offline mockのno-replace予測を実差分の代用にしない。

## OutcomeUnknown / EvaluationFailed

専用test、承認済み安全な合成データとfault入力で実施。実AI課金は別の明示許可が必要。Cloudでは限定数学モデルを検証しただけでCloudWatch受入PASSではない。

- [ ] Worker単独のOutcomeUnknown >=1 → 既存OutcomeUnknown ALARM・SNS到達。
- [ ] Dispatcher単独・両者同時でも同じAlarm。名/address/topic不変、2MetricStat/60秒/Sum、1-of-5。
- [ ] Worker単独のEvaluationFailed >=1、Dispatcher単独、両者同時 → customer既存evaluation-failed ALARM。
- [ ] 失敗1件のみで検知し、M=2や最低件数gateを誤って導入していない。
- [ ] 正常無通信・片側系列欠測で誤ALARMを出さない。RecoveryHeartbeatのmissing=breachingは維持。
- [ ] timestamp付き遅配（60/120/240秒）を投入し、時刻/到着/評価/ALARM/SNS時刻を記録。
- [ ] 5分以上の遅配限界も記録し、検知を保証しない。運用SLOに足りなければ受入FAILとして別レビュー。
- [ ] 失敗後に新しいbreachがないときのOK復帰時間とSNS到達、CloudWatchの追加datapoint取得挙動を確認。
- [ ] test failure-rateはFILLなし、900秒1-of-3、最低10件・>20%が維持される。単発件数Alarmの代わりにしない。
- [ ] developer17/18参照、customer21/23、test39/43。既存17 Alarmが削除・簡略化されていない。
- [ ] 新metric名/高cardinality dimensionsなし。実Tokyo SKU/無料残枠/実請求の参照課金を確認。

## test閉鎖と再開

- [ ] 39 Alarmを保持し4入口を閉じ、外部Invoke/DDB writerも停止。Worker mapping2、Lambda unreserved=-1を保つ。
- [ ] 全aliasのasync event age（設定なしなら6h）+timeout経過。処理中Lambdaや期限内のfuture retryを「0 metric」だけで否定しない。
- [ ] 主queue/worker DLQ/stream failureのvisible/inflight/delayedを観測し、概算0だけを証明にしない。全queue ledgerを独立照合。
- [ ] base table全ページConsistentRead scanでprocessing/未完Dispatch/将来next_atを検出。GSI0のresult consistencyを信用しすぎない。
- [ ] OUTCOME_UNKNOWNの全owner/evaluationをincident資料で解決。DLQ未解決なら削除不可。
- [ ] Scan/GetFunctionEventInvokeConfig等のread権限あり。権限不足をempty扱いしない、boundary/WIFを無断拡張しない。
- [ ] 観測と独立承認にAccount/Region/run_id/manifest hash/State identityが完全一致、最大15分TTL。古いproofを再利用しない。
- [ ] bool confirmed=trueだけのplanが拒否される。不正hash、別State/Account/run、staleも拒否。
- [ ] saved planは正確な39承認Alarm deleteだけ・全baseline no-op・outputだけmonitoring=false/confirmed=true/proof hash。
- [ ] guarded preflight後にState/version/hash/lockを変えた場合applyが拒否される。apply直前にexpiry/hashも再検査。
- [ ] 途中失敗・通信断・readback不一致後、同じdirectory/proofで再applyできない。read-only診断へ移る。
- [ ] 成功後、同じlineage・serial増加・新VersionId、Alarm0とbaseline全属性/Artifact/alias/Provider不変。
- [ ] 再開は4入口falseのまま39を復元してreadback。confirmation/proofを解除。全39の作成・SNS準備が入口有効化より先行。

## 管理・Auth・履歴

- [ ] 管理成功はQuestionBankChange exact SYSTEM/OP key、owner/request UUID/schema/reply200。別人・別requestを証拠にしない。
- [ ] business record観測とIAM ConditionCheck直接実証を分け、未観測の直接実証をPASSにしない。
- [ ] 1問sessionの409 SESSION_COMPLETED、複数問の2問目200、無問題カテゴリ409 CATEGORY_UNAVAILABLE、同一replay・改変409を確認。本番問題bankをテストのため変更しない。
- [ ] 91日以上の実存Evaluationを本人確認後exact読取。古schema/failed、退会Cognito、DDB item削除時unavailableを確認。
- [ ] summary/通常ログに回答全文・採点本文・secretがない。private出力は最小担当者だけに公開、本人確認proofは期限付き。
- [ ] 回答/採点/処理record TTLなし、新table/履歴writeなし。PITRは現状無効のまま方針を別途承認。
- [ ] Tokyo PITR/復旧単価、table/LSIサイズ、35日window、RPO/RTO、削除済み本人情報の復元防止を評価。90日履歴存続と混同しない。

## 公開可否

- [ ] cold-start p95=2003.466ms >2000msのFAILを、正式な新証跡で解消（現時点FAIL継続）。
- [ ] 実AI30人同時の既存Gateを検証（現時点未検証）。Worker2/Scheduler毎分/性能閾値は緩和しない。
- [ ] 全受入とSNS到達、本人確認/削除/PITR方針が揃うまで公開準備完了とは判定しない。
