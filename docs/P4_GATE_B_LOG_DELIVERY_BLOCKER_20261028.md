# Gate B Stage更新の実効IAM不足

2026-10-28 JST。実測sourceは `05f4f1be8bead2cede7d9b62810650b8af4bf1f0`。
Gate Bは未完了。本資料・PRはIAM変更の実行承認やApply成功証拠ではない。

## 実行と現在状態

- PR [#71](https://github.com/yonegen0/ai_interview/pull/71)、[#72](https://github.com/yonegen0/ai_interview/pull/72)は通常merge済み。
  mainのBackend・Frontend・Terraform offline・候補toolchain CIは成功。
  Backend 3,367件、API契約102件、Frontend 670件、Mock E2E 37件が成功した。
- 新規Plan [40666099393](https://github.com/yonegen0/ai_interview/actions/runs/40666099393)はattempt 1成功。
  全77 managed resourcesの監査はadd 0 / change 1 / destroy 0 / replace 0。
  Stageログ形式以外の実構成変更はなく、固定Artifactを再利用した。
- 独立readerは最初にlock hashのCRLF/LF差で停止した。元のsealed scopeと停止記録を保持し、
  固定commitのGit blobとの厳密照合を明記した補足readbackで成功した。Plan再実行はない。
  補足readbackは36 SDK / 36 HTTP、State13不変・lockなし・4入口閉鎖。
- 新規Apply [40667076073](https://github.com/yonegen0/ai_interview/actions/runs/40667076073)はattempt 1失敗。
  CloudTrailの09:50:53 UTCの`UpdateStage`は`BadRequestException`であり、応答のmessageは
  標準deploy roleに`logs:CreateLogDelivery`のidentity-based Allowがないことを示す。
  ログ変数の不正やGitHub認証失敗と推定しない。
- 独立readbackではState serial **14**、同じlineage・新しいS3 version、77資源とmanifestを確認。
  State差分は既に許可済みのProviderキャッシュrefreshだけであり、AWSのStage形式は4項目のまま。
  `apply-started` receiptあり、`apply-completed` / `deployment` receiptなし。
  Terraform正常終了・Gate B成功とは扱わない。
- 最終診断は21 SDK / 21 HTTP、State before/after一致・lockなし、API/Worker/Streams/Scheduler閉鎖。
  dev-plan/dev-applyのreadiness全4項目false、cleanup error 0。
  失敗したApply・Planの再実行、State手動編集、force-unlock、入口開放、実AIは実施していない。
  過去の元ApplyのUNKNOWN記録も変更していない。

## 実行前の修正案

`standard_ci_stage_log_delivery_enabled=false`を既定にする。
別途承認を受けてtrueを指定したBootstrapのPlan/Applyだけで、
`ai-interview-standard-ci-deploy`の`standard-deploy` policyへ次の1 statementを追加する。

| 項目 | 提案 |
| --- | --- |
| Action | `logs:CreateLogDelivery`, `logs:PutResourcePolicy`, `logs:DescribeResourcePolicies` |
| Resource | `*`（これらのactionはresource-level指定をサポートしない） |
| Condition | `aws:RequestedRegion = ap-northeast-1` |
| 付与しないrole | standard plan、両artifact、legacy、test、runtime |
| 変更しないもの | 信頼/OIDC/Boundary、API公開、Lambda、既存Artifact、Secret、lock/State操作方式 |

実roleのpolicyでは上記3 actionがすべて欠落している。
既存のaccount-level resource policy一覧にも対象log groupへ一致するAllowは見つからなかった。
これはRESOURCE-scope policy全件不存在の証明ではない。AWSの自動policy設定が必要な場合も
まとめて対応できるよう、CreateだけでなくPut/Describeを含めた。
既存の`logs:DescribeLogGroups`と対象log groupの作成権限は再追加しない。
今回のStage設定に不要なlog delivery削除/更新、ログ本文取得、追加IAM操作は追加しない。
`PutResourcePolicy`はTokyo内のaccount-level log resource policyを変更できるため、
対象Stage ARNだけへの権限制限とは表現しない。この権限拡大は現在の包括承認の対象外。

根拠は[AWS HTTP API logging](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html)、
[CloudWatch Logs初回設定に必要な権限](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AWS-logs-infrastructure-CWL.html)、
[Logs IAM resource対応表](https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html)。
API Gatewayのドキュメントにある全lifecycle actionを無条件で追加せず、
CloudWatchの初回setupに必要な3 actionに限定した提案である。実効IAM成功は未検証。

Stage recovery descriptorはState13に加え、今回読戻したState14を明示的に扱えるようにする。
State identity全4値・snapshot hash・全資源coverage・Stage形式・入口閉鎖の検査は保持する。
旧State13 descriptorでState14を受け入れず、serial15以上への自動追従も許可しない。
新State14で不要になったpolicy cache refresh flagや旧Deployment pinを再利用しない。

## 承認後の再開順序

1. このPRの固定HEAD・CIと上記IAM差分を承認し、通常mergeする。
2. Bootstrapの現State/lock/実policyと固定inputsを照合し、正規の既存Bootstrap経路で新Planを監査。
   対象は上記standard deploy inline policyの更新1件だけ。追加・削除・replaceや別IAM差分は拒否する。
   Bootstrap Stateには今回接続しておらず、saved Plan/hashを架空に確定しない。
3. 新saved Bootstrap Planを1回Applyし、policy/readinessを読戻す。
   候補codeと正式Bootstrap実行経路の条件が合わなければ実行しない。
4. 現dev State14の新VersionId/hashとsnapshotを固定した新descriptorを作り、
   新sourceでStage形式のみの新Planを1回監査し、その新バイナリだけを1回Applyする。
   Plan008・失敗Apply008・消費済み承認は再利用しない。
5. State/receipt/Stage/4入口/readinessを独立確認し、その後に次工程へ進む。

同じ確認を工程ごとに要求する目的ではなく、上記IAM拡大と限定復旧を一括判断できる提案である。
不明Applyの再送や手動State修復の承認は求めない。

## 開発・公開準備の残作業

Frontend/API契約/認証境界/Coaching V2/STAR/質問管理/復旧の既存offline CIは再利用する。
今回の調査で新しい製品P0/P1の再現はなく、無関係な機能修正や依存更新は追加しない。
実Cognito OTP/refresh/JWT/本人分離、実AI品質・費用、30人性能、実frontend接続、Hosting/公開受入は未完了。
既存の有限smoke手順は[STAR live adapter](STAR_V14_LIVE_ADAPTER.md)、
性能の既存FAILは[性能解析](P4_DEV_PERFORMANCE_ANALYSIS_20261006.md)を維持する。
Bedrock採用方針を実配備・実推論成功へ読み替えない。
