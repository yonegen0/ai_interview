# P4 dev 一時検証・条件付き自動Closure 承認テンプレート

以下をEnablement apply承認プロンプトに含める。Enablementのplan path・SHA・HEAD・State基準は
監査済み証跡から記入し、placeholderのまま実行しない。ClosureのSHAは検証後の最新Stateから作る
saved planで確定するため、今回の承認はそのSHAを先に推測するものではない。

```text
P4 devの一時的なSmoke / Performance Validationを実行してください。

Enablement saved plan: <監査済みsaved planの絶対パス>
SHA-256: <監査済みSHA-256>
期待Git HEAD: <mainとorigin/mainが一致するcommit>
Account / Region: <照合済みdev Account> / ap-northeast-1
State基準: <lineage / serial / VersionId / resources>

このEnablement saved planを1回だけapplyすることを明示承認します。
Git・Account/Region・backend/provider・State・lock・State外dev resource・Artifact・差分を
読み取り再確認し、すべてPASSなら途中確認なしで進めてください。

Enablement apply成功後、Smoke、承認されたPerformance、必要なSNS等の検証、証跡保存、
Closure plan作成・全件監査、Closure apply、AWS閉鎖読戻しを1回の作業で完了してください。
Smoke/PerformanceがFAILでも、StateとAWSが正常ならClosureへ進んでください。

以下をすべて満たすClosure saved planについても、追加承認なしのapplyを1回だけ事前承認します。
- create=0 / replace=0
- updateはAPI endpoint enabled→disabled、Worker Enabled→Disabled、
  Streams Enabled→Disabled、Scheduler ENABLED→DISABLEDの4resourceのみ
- destroyは今回のvalidation用CloudWatch Alarmのみ
- Lambda code/version/alias/Artifactは最新成功配備のものを保持し、rollbackしない
- Cognito/DynamoDB/SQS/SNS/IAM/runtime/architectureは維持
- Worker MaximumConcurrency=2、backend、providerを維持
- Account/Region一致、State整合、State外dev resourceなし、active lockなし

ClosureのSHA-256はapply前に算出・記録してください。
許可差分を外れる変更、State不整合、State外resource、lockなどがあれば、applyせず
差分と理由を報告してください。EnablementまたはClosure applyがpartial failureした場合も
再apply・新plan・destroy・import・State操作・AWS手修正はせず、read-only診断で停止してください。

成功時の最終状態は、API disabled、両mapping Disabled、Scheduler DISABLED、
validation Alarm 0、lockなし、State外dev resourceなしとしてください。
性能やinbox未確認を理由にactive状態で通常の作業を終えないでください。

正式performance gateと限定試験での実用性を分けて報告し、基準を変更しないでください。
性能レビューが残る場合はclosed状態で性能検証フラグを維持してください。
閉鎖後の原因分析は既存証跡とコードの読み取りのみで行い、再有効化・再負荷試験・
Terraform/application変更・Artifact build/upload・memory/concurrency/PC変更は実行しないでください。
```

現行の閉鎖update対象は次の4address。各`change`の実値で方向を確認する。

| Address | 閉鎖変更 |
|---|---|
| `module.service.aws_apigatewayv2_api.main` | `disable_execute_api_endpoint: false → true` |
| `module.service.aws_lambda_event_source_mapping.worker` | `enabled: true → false` |
| `module.service.aws_lambda_event_source_mapping.streams` | `enabled: true → false` |
| `module.service.aws_scheduler_schedule.recovery` | `state: ENABLED → DISABLED` |

Alarm削除対象は、承認されたEnablementで検証に必要とされたAlarmの一覧と照合する。
単にresource typeがCloudWatch Alarmであるだけでは削除を許可しない。
計算属性やoptional値のrefreshも根拠を記録し、説明不能な差分を黙認しない。
