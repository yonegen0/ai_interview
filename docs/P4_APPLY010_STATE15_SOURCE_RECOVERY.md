# Apply010原因対応sourceとState15復旧schema

Apply010はUpdateStageのログ配信権限不足で失敗した。
根拠と診断修正は[失敗分析](P4_APPLY010_FAILURE_ANALYSIS_20261029.md)と
[PR #77](https://github.com/yonegen0/ai_interview/pull/77)を参照する。

2026-10-29 JST、固定提案SHA256
`2281928ff8ceb6b83a5f80731506955005fdffb64c2510d9de12894021d1a70b`に対する
source修正・通常PR・必須CI・通常mergeのみの明示承認を受領した。
この承認はAWS接続・IAM配備・Terraform init/plan/apply・State/readiness変更・
旧Plan/承認の再利用・実AI・公開を含まない。元のprivate提案・承認・証跡は上書きしない。

## 権限の最小修正

既存のopt-in `DevStageLogDelivery`へ`logs:ListLogDeliveries`だけを追加する。
CloudTrailの相関済みUpdateStageレスポンスがこのアクションのAllow欠落を明記した。
[AWS公式ログ設定](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html)
も同権限を列挙するが、ほかの未実証アクションは追加しない。

既定false、standard deployロール限定、東京Region条件、既存Resourceと他のstatementを保持する。
HCL sourceをmergeしても実IAMは変更されない。他のAWS制約がないことや次回Apply成功は未検証。

## State15の独立したdescriptor

既存schema1のserial13/14と既存互換性は維持する。schema2だけがserial15を扱い、
既存のartifact・Stage4→6・snapshot/identity・closure制約に加え、次を必須とする。

- Apply010のsource、失敗Run/Attempt、Plan Run/hash、開始receipt hashを固定する。
- 完了/deployment receipt不在、旧承認消費済み、拒否アクションを固定する。
- private CloudTrail相関証拠hashと、同lineageのState14→15の別version/hashを結び付ける。
- 全77資源のcached属性fingerprintとdescriptorのState15 identity/snapshotを照合する。
- 旧policy-cache-refresh例外と旧Deployment pinを受け付けない。

レビューで、候補の共通Stage検証がDeployment pinの2項目を揃えると受理する余地を発見した。
承認資料の「旧pinを持ち込まない」という制約に合わせ、schema2ではその経路も拒否する。
旧schemaの例外は拡張しない。

predecessor内の旧Plan hashは失敗証拠の相関用で、旧Planの実行許可ではない。
schema2は証拠の新規取得や承認生成を行わない。descriptorの証拠hash・identity・fingerprintは
別途監査し、新しいsource/descriptorに対する承認hashで固定する。
このschemaだけでは旧承認や旧receiptを新しい実行へ継承できない。

Plan監査はStage以外の全資源no-op、置換/削除/unknown拒否、全資源の完全coverageと
既存の限定された表現差の検査を維持する。State15の導入でIAM変更をdev Planへ許可しない。
CIのfixtureは合成した77資源であり、private State・実識別子・rawイベントを含まない。

## 新Plan前の条件

1. 通常PR・必須CI・merge後CIを確認し、新しい正確なmain SHAを固定する。
2. 新しい限定読取り承認で、canonical bootstrapの最新State/lock/40資源/IAMと、dev State15/
   lock/Artifact/Stage/closure/readinessを照合する。消費済みCloudTrail承認は転用しない。
3. [Stage2 native canonical-bootstrap経路](P4_STANDARD_STAGE2_MIGRATION.md)で新Plan承認を得る。
   standard deploy policy 1更新だけのSaved Planを独立監査し、正確なPlan hashへの別Apply承認を得る。
   反映後に実policy・State・lock・readinessを確認する。
   歴史的32資源のS3版読取り修復専用`bootstrap_maintenance.py`へこの差分を渡さない。
4. 最新dev State15のidentityが保存証拠と一致する場合だけ、新source/descriptor/hashを固定して
   新dev Plan承認を得る。不一致ならこの下書きを再利用せず再監査する。
5. 新dev Saved Planを全77資源・Stage4→6のみ・IAM10資源no-op・その他add/destroy/replaceなしで
   独立監査する。その後に別の正確なApply承認と事後検証を行う。

State15が正式な現在状態。State14への巻戻し、serial guardの単純差替え、Plan010・旧承認の
再利用は禁止する。入口閉鎖・readiness全falseは最終保存証拠に基づき、sourceのCI成功を実AWSの
反映・実効IAM成功・Gate B完了・公開可能の証拠として扱わない。
