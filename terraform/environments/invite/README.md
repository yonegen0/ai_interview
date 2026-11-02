# 招待MVP: 独立したg1環境

採用候補はClaude Haiku 5.5直接API。既存devの更新より、新環境を選ぶ。
devの停止・writer・過去ledgerが未確定で、同じtableの空counterを安全な会計開始と扱えないため。
既存service/frontend moduleを再利用し、過去履歴の完全復元を待たずに配備準備を進める。
**ソース実装は実AWS隔離・受入・公開の証明ではない。RELEASE_HOLDを維持する。**

2026-11-02の現行受入はrevision003、既存ADMIN 1名＋USER 1名、OTP最大2通、固定6有料ケース。
最新の状態・会計coverage・Phase 6残差・承認境界は[MVP公開受入マトリクス](../../../docs/MVP_LIVE_ACCEPTANCE_MATRIX_20261029.md)を参照。
Phase 5 CはNOT_RUN。過去B/D成功から現在の閉鎖権限・公開可能性を推定しない。

## 構成

- 固定世代`g1`、prefix `ai-interview-invite-g1`、専用S3 State key `invite/g1/terraform.tfstate`。
  旧Stateの移行・import・旧データコピーはしない。次世代は別root/keyで準備する。
- DynamoDB/Stream/3 Queue/4 Lambda/5 runtime Role/Cognito poolとclientを新設。
  tableをledger世代境界とし、通常評価・Coaching・STARの既存共通UTC月20/600予約を再利用する。
  送信結果不明は予約を返さず、自動再推論しない。過去会計はUNPROVENのまま。
- 新runtime boundaryは新世代の資源に限定。table/Stream/Queueは他世代Roleを明示Deny。
  resource policyのoperator例外は承認済みの正確なRole ARNのみ。旧runtimeを指定できない。
- Secretは新規の専用名、読取りは新Workerのみ。値・APIキーをTerraform/State/tfvarsへ書かない。
  専用Anthropic workspaceと新キーを使用。旧キーを新環境へコピーしない。
- 非公開S3/OAC/HTTPS CloudFrontは既存frontend moduleを再利用、旧web bucketとは別。
  CORSは新CloudFrontの正確なHTTPS originを自動参照し、追加は明示HTTPS originだけ。
  Cognitoは招待専用、USER/ADMIN/JWTは既存契約を保持。
- customerログ14日、table削除保護/PITR。入口有効時は既存customer用21 alarmを世代別EMFで監視。
  AWS通知予算は最大$10/月。通知は強制課金停止ではなく、Anthropic料金も含まない。
- 全入口、保全準備、quarantineはdefault false。初回closed planは旧資源を変更しない。

## 承認・実行順

既存[P4 Runbook](../../../docs/P4_TERRAFORM_RUNBOOK.md)と対象SHA・入力hash・saved Plan別承認を守る。
このrootを既存dev向けP4実行器に渡してguardを回避しない。現CIはオフライン検証だけを追加する。

1. 固定SHAのLinux ZIPを生成してdigestを記録。既存のprivate保存State/資源inventoryを再利用し、
   対象Account/短期Role、artifact bucket/VersionId、SES、通知先を継承する。
   最小read-only確認と新rootのinit/planは実行パッケージ承認後。旧75要求の全policy探索はしない。
   backendは既存versioning/encryption/lockingを利用するが、**keyが新規**であることを確認。
   workspaceはdefault。既存dev/bootstrapのState書換え、bootstrap権限拡張を含めない。
2. 4入口/frontend/quarantine=falseでclosed saved Planをレビュー。新規資源のみ、replace/destroyなし、
   secret値なし、隔離policy・専用boundary・Artifact一致を確認してから別途Apply承認を得る。
   初回作成は継続課金資源を含む。成功時はState・policy・alias・閉鎖を読戻す。
3. 旧API/Scheduler/2 mappingの閉鎖を維持。**concurrency=0より先に**
   `legacy_preservation_enabled=true`の別Plan/Applyでlegacy専用archive queueと旧4 RoleのSendMessageだけを準備。
   全対象関数/alias/使用versionのasync設定を照合し、既存destinationがあれば勝手に上書き・importしない。
   未設定と確認できた対象だけを`legacy_async_targets`に指定し、on-failureをarchiveへ設定する。
   旧native処理の追加retryは0。全対象のdestination・送信権限・保存経路を独立読戻ししてから停止へ進む。
   archiveにはconsumer/redriveを作らない。最大14日なので期限内に暗号化private証跡へ退避し、
   実行中・既存SQS/DLQ/Stream失敗もprivate保全する。purge、旧データの新work queueへのコピー、未知推論の再実行をしない。
   その後、旧4 Lambda全版への新規実行をreserved concurrency=0で停止し、実行中timeout経過を確認する。
   `legacy_quarantine_enabled=true`の別saved Plan/Applyで既知5 Roleの書込み・有料AI・credential取得をDeny。
   archiveへのSendMessageだけは保全用に残し、受信/削除/redriveを旧Roleに許可しない。
   外部Providerの旧キー/旧workspace権限を失効し、cached keyによるHTTP送信も止める。
   IAMだけではcached外部キーを止められない。**独立読戻し成功前に入口を有効化しない。**
   quarantineは削除保護付きで、closure時もtrueを維持する。旧環境の再開は別承認。
4. 新専用workspaceの支出制限/キーを確認し、Secretへ安全な手段で投入。
   実workspace制限の有効性と設定可能な最小額を確認する。APIキーはログ・コマンド引数へ出さない。
   当月の旧新合計が不明なまま20/600上限の保証を省略しない。
   11月の完全coverageは未成立であり、新baselineや支出制限だけでは代替できない。
   現証拠での最短候補は12月1日09:00 JST以降の新UTC期間。期間開始前からの旧writer隔離継続と
   独立coverageが必要であり、月替わりだけで有効化しない。
5. 隔離・停止・監視通知・支出制限の読戻し後、別enable Plan/Applyを承認する。
   現行の受入は既存管理者1名＋USER1名、最大**6有料送信**（通常評価2、Coaching2、STAR2）、
   provider/networkの自動retry 0。重複・上限超過・認可拒否は有料送信を増やさず検証する。
   HTTP transport/Worker timeout、結果不明、請求上限不明、本人分離失敗で有料試験停止。
   通常/Coachingは4096、STARは既存2048 output token上限。入力/価格を実行前に固定し、
   **推論見積枠$0.05**を超えるなら開始しない。請求hard capの保証ではない。
   JWT、USER/ADMIN、ADMIN/USER間の他本人拒否、20/600境界、冪等、HTTPS/CORS、Alarm/停止を実AWSで確認。
   USER/USER分離はこの2名では未実施。追加USERと必要なOTP等を別scopeで承認し、公開前に確認する。
   20/600境界は既存オフライン原子予約試験を再利用。有料600送信やledger巻戻しはしない。
   実tableへの合成予約による境界試験は現行6ケースscopeに含めず、必要ならcoverageを保つ別承認とする。
6. 受入結果・残余リスク・初期招待の確定対象/人数/送付文をまとめ、最新公開Planと別の公開・送信承認を求める。
   今回のC/Dは招待0・公開0。現行2名から無断で人数を拡大しない。
   UI追加改善/独自ドメイン、過去ledger完全復元は後続。Fake p95=2,003.466msのFAILは保持し、
   実Claude性能と公開必要基準の正式判断を残す。PR #43 HOLDは維持する。

## 停止・復旧

一時受入の成功/失敗後は、承認範囲内で4入口とfrontendをfalseへ戻して独立読戻し。
quarantine、DDB/Queue/Secret/Role、データ、証跡は保持する。入口falseだけで直接Invokeは止まらないため、
異常時の新4 Lambda concurrency=0とキー失効も事前承認へ含める。
Apply部分失敗/State不整合/未知差分なら再Applyやdestroyで修復せず、証拠を保持して停止する。
旧環境を自動復旧先にしない。

## オフライン検証・公式仕様

既存`backend/skills/p4/offline_terraform.py`がcredentialを除去した新規コピーでvalidate/Mock testする。
実AWS Plan/Applyとは別。Terraform1.14.9、AWS6.65.0 lockをdevからそのまま再利用、依存更新なし。

- [DynamoDB resource policy・Role条件](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/rbac-examples.html)
- [DynamoDB対応API](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/rbac-iam-actions.html)
- [SQS DLQ/redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Lambda native async保全とconcurrency=0](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-retain-records.html)
- [Haiku 5.5モデル・料金](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

料金は2026-11-01確認時、入力100k token以下で$0.10/MTok入力・$0.50/MTok出力。
試験入力を1送信100k以下、出力4096以下と保守的に置けば6送信は$0.072288以下となり$0.05枠に収まらない。
開始前に実payloadのより小さい入力上限を固定して再計算する。少数試験の目安は入力20k以下なら
6×(20k×$0.10+4096×$0.50)/1M=$0.024288。税・API外費用は別。
