# P4 dev の一時検証と自動Closure

ユーザーの最新指示を優先する。P4 devのSmoke / Performance Validationでは、
[承認テンプレート](docs/P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)と
[Terraform runbook](docs/P4_TERRAFORM_RUNBOOK.md)を使用する。

- Enablement承認には、検証後の条件付き自動Closure承認を同時に含める。
  個別に承認されたEnablement saved planは、指定SHA-256一致を確認して1回だけapplyする。
- Enablementが成功し、StateとAWS実体が正常なら、Smoke・PerformanceのPASS/FAIL、
  EMAIL_OTP/SNSのinbox未確認にかかわらず、証跡保存からClosureまで同じ作業で完了する。
- Closureは最新成功applyの入力から4フラグだけfalseへ戻す。最新Artifact・Lambda版・aliasを保持する。
  saved planを全件監査し、apply前にSHA-256を記録する。新しいClosure planのSHAが承認時に
  未確定でも、同時承認された以下のホワイトリスト条件をすべて満たせば、追加承認なしで1回applyする。
- 許可差分はcreate=0、replace=0、API endpoint・Worker mapping・Streams mapping・Schedulerの
  閉鎖4updateと、その検証用CloudWatch Alarmの削除だけ。その他のbaseline resourceはno-op。
  Lambda code/version/alias/Artifact、Cognito、DDB、SQS、SNS、IAM、runtime、architecture、
  Worker MaximumConcurrency=2、backend、providerを維持する。
- Account/Region一致、State整合、State外dev resourceなし、active lockなしも必須。
  ホワイトリスト逸脱・不整合・lockがあればapplyをせず、具体的な差分と理由を示してユーザーへ戻す。
- EnablementまたはClosure applyがpartial failureした場合は再applyや手動修復をせず、read-only診断で停止する。
- 成功時はAPI disabled、両mapping Disabled、Scheduler DISABLED、validation Alarm 0、lockなし、
  State外dev resourceなしを読み戻してから結果を報告する。通常の作業終了状態はclosed。
  性能レビュー待ちだけを理由にactive状態で作業を終えない。
- 性能Gateは後付けで変更しない。正式Gateと限定試験での実用性を区別する。
  閉鎖後の分析は既存証跡・コード・公式資料の読取りで行い、再有効化や再負荷試験は別の明示承認まで行わない。

2026-10-06のユーザー指示で、この条件付き自動Closure運用へ変更済み。
