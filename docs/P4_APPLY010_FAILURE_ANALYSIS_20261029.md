# Apply010: UpdateStageログ配信権限不足と診断修正

対象source: `c25181ca3880825a9dffd59115bc79cb450c80c0`。
失敗[Run 40777680174 / Attempt 1](https://github.com/yonegen0/ai_interview/actions/runs/40777680174)。
元のprivate証拠、State、Saved Plan、承認、receiptは変更しない。

## 確定した原因

別途明示承認されたCloudTrail限定読取りで、2026-10-28T22:11:51Zの
`apigateway.amazonaws.com / UpdateStage`が`BadRequestException`を返したことを確認した。
固定Account/東京Region/対象API/devと、当該Runのdeployロールセッションが完全一致する。
Terraform user agent、6項目のログformat、既存destinationとの一致もprivate領域で照合する。
requestID・主体ARN・API識別子・レスポンス原文はprivate領域だけに保存する。

イベント直下の`errorMessage`は欠落していたが、`responseElements.message`に
ログ有効化権限不足と、identity-based policyによる`logs:ListLogDeliveries`の許可欠落が明記されていた。
したがって直接原因はUpdateStageに伴うログ配信権限不足である。
これは通常のUpdateStage認証自体の拒否を示す証拠ではない。

読取り提案SHA256は`83aa9611f1d3076ec4646229e582a4b57a3e205cd650897baf8cf127aa4e4ca5`。
実績は1ページ、対象イベント1件、SDK/HTTP各3回（SSO/STS/LookupEvents）、再試行0、AWS書込み0。
読取り範囲を追加拡大していない。

## 最終証拠の相互照合

| 証拠 | 結果 | 意味と限界 |
| --- | --- | --- |
| State14→15 | lineage維持、serial/version/hash進行、77資源のaddress/cached属性同一 | State進行はApply成功の証拠ではない |
| 最終State15の前後読取り | identity同一、lock不在 | 当時の読取り内で安定。現在のAWS再照会ではない |
| 実Stage | requestId/routeKey/status/responseLengthの4項目 | 6項目化は未反映 |
| State14/15のcached format | 上記にrequestTimeEpoch/responseLatencyを加えた6項目 | 実Stageと不一致 |
| Saved Plan010 | 実Stage4→6項目、add0/change1/destroy0/replace0、IAM10資源no-op | 逆向きPlanではない。旧Plan再利用は禁止 |
| receipt | apply-startedあり、apply-completed/deploymentなし | 単回承認消費済み、再Apply不可 |
| 入口/readiness | API閉鎖、Worker/Streams Disabled、Scheduler DISABLED、readiness全false | 最終保存証拠による状態。新たなreadiness操作なし |

## 仮説の分類

| 優先 | 判定 |
| --- | --- |
| A: ログ配信権限不足 | 確定。拒否アクションはListLogDeliveries |
| B: UpdateStage APIエラー | 確定。BadRequestExceptionはAに起因 |
| C: 子プロセス/認証/時間制限 | TerraformからAWSへの要求到達は確認。実終了コードと終了観測記録は未回収でUNKNOWN。タイムアウトを原因とする証拠なし |
| D: Apply成功後の検証不一致 | 今回の直接原因ではない。API更新自体が失敗。現コードの失敗経路も事後検証へ到達する前に非ゼロを拒否する |
| E: その他 | ListLogDeliveriesを追加した後の実AWS成功や他の不足権限がないことまでは未検証 |

旧`apply_process`はstderrを破棄し、非ゼロ終了も汎用`require`経由で
`StageRecoveryScopeMismatch`とした。最後のcheckpointがreadiness-readbackのまま残るため、
公開診断のstage=readiness-readbackは実失敗箇所を表していない。
開始receiptはPopenより前に書かれるため、それだけで子プロセス開始を断定しない。
今回はCloudTrailのTerraform要求が開始/実行の独立した裏付けとなる。

## 公式仕様と最小修正案

採用版はTerraform 1.14.9、dev AWS Provider 6.65.0、Python 3.14.9、boto3/botocore 1.43.118。
[AWS HTTP APIログ設定](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html)は
CreateLogDelivery/PutResourcePolicy/UpdateLogDelivery/DeleteLogDelivery/CreateLogGroup/
DescribeResourcePolicies/GetLogDelivery/ListLogDeliveriesを列挙している。
既存DevStageLogDeliveryはCreateLogDelivery/PutResourcePolicy/DescribeResourcePoliciesの3つ。
CreateLogGroupとDescribeLogGroupsは既存の別statementから許可される。
UpdateLogDelivery/DeleteLogDelivery/GetLogDelivery/ListLogDeliveriesの4つはsource上のdeploy権限にない。
閲覧用のDescribeLogStreams/GetLogEvents/FilterLogEventsも公式例にあるが、dev deployへ一括追加しない。

根拠がある修正案は、既存のopt-in DevStageLogDeliveryに`logs:ListLogDeliveries`だけを追加すること。
東京Region条件、既存Resource、他ロールへの非適用を保持し、他の欠落アクションは推測で追加しない。
実IAM変更には[Stage2のnative canonical-bootstrap経路](P4_STANDARD_STAGE2_MIGRATION.md)での
新しいPlan/監査/Apply承認と実効権限確認が必要。
歴史的32資源のS3版読取り修復専用`bootstrap_maintenance.py`へこの差分を渡さない。
この診断PRはTerraform/IAM、State15 admission、承認、readinessを変更しない。

追加2変数も[AWS HTTP APIログ変数](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging-variables.html)
に記載されている。未対応変数であるとは判定しない。
[Provider 6.65.0のStage実装](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/stage.go)
はUpdateStageエラーをTerraform診断として返す。実exit codeそのものはこの仕様から補完しない。

## 診断修正

- admission時に以前のプロセス観測をリセットし、Popen成功後に開始、communicate成功後に終了コードを記録する。
- 非ゼロ、起動失敗、期限停止、観測例外、journal失敗に有限の理由コードを返す。
- 停止時のSIGINTと既存120秒の終了待ち、UNKNOWN時の再試行禁止を維持する。
- Apply完了記録、receipt転送、実行後検証を別stageにする。実行後検証失敗はApply exit=0と区別できる。
- 非ゼロ時は既存の有限marker/出力hash/長さだけをprivate記録し、公開診断には許可済みmarkerだけを出す。
  markerは原因の確定証拠とは扱わない。生stdout/stderr・例外本文・引数・資格情報は公開しない。

既存diagnostic-only.patchは起動/終了booleanを改善するが、終了コード、例外分類、
タイムアウト、実行後検証の区別を欠くため、そのまま適用せず上記を追加した。
旧6テストに依存せず、成功/非ゼロ/起動拒否/期限/例外/記録失敗/機密非公開/事後検証の回帰試験を行う。

## 新Plan前の必須条件

1. 診断修正の通常PR・必須CI・通常mergeを完了し、固定した新sourceを使う。
2. 上記1アクションのIAM修正を別途レビューし、canonical bootstrap保守の承認境界で反映・確認する。
3. 正式な現在状態はState15。新しい限定承認によるState15/version/hash/lineage、lock不在、
   API/dev/Artifact/closure/readiness/実効IAMの新鮮な照合が必要。
4. State15用の復旧sourceとdescriptorは、失敗Run/Plan/開始receipt/CloudTrail証拠をpredecessorとして
   固定し、77資源不変・Stageのみ4→6・IAM no-op・旧承認不継承を再監査する。
   現行のserial13/14 guardを単に15へ差し替えることを禁止する。
5. 新source/descriptorに対する新Plan承認を取得し、生成した新Saved Planを独立監査する。
   新Apply承認はその後に分離する。State14への巻戻し、Plan010/旧承認/receiptの再利用はしない。

診断修正やMock/CI成功だけでは、AWS原因修正済み・Gate B完了・公開可能とは報告しない。
