# 自律開発方針（2026-10-24、本人指示）

通常の開発・検証に必要なbranch/PR/CI、GitHub保護を満たす通常merge、開発AWSの整備・検証を連続実行する。
過去のD親承認・固定patch・期限・操作回数・全bypass actor完全性・将来請求USD0保証を、通常PRの独自停止条件にしない。
旧成果・消費記録・監査証跡は保全する。新しい方針を旧承認の再利用や旧CMS仕様の成功と表示しない。
無料対象runner、容量制限付きArtifact、短期保持、既存予算を使い、有料runner・課金設定変更・無料枠超過保存を自動実行しない。
Terraformは新しいsaved Planを独立検査し、同じbinaryだけをApplyする。State/lock/対象・IAM差分を確認する。
保護迂回、予期しない削除/置換・権限拡大、Secret原本不足、漏洩リスク、想定外継続課金、State/Plan不整合、
重複リスクのある結果不明、重大な品質失敗、予期しない本番データ/公開範囲変更では該当工程だけ停止する。
main直push・force・秘密鍵探索・原本捏造は禁止。独立した安全な作業は継続し、本人判断事項を一括報告する。
以下の過去手順と相違する場合はこの方針と最新の本人指示を優先し、Closure・本人別分離・API互換・最小権限を維持する。

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

# 自律開発・例外時停止（Ver.2.0、2026-10-11）

詳細は[自律実行ルール](docs/CODEX_AUTONOMY_RULES.md)を参照する。
- 依頼範囲内の調査・実装・原因修正・重点検証・隔離worktree・資料更新は個別確認せず完了する。
  成功済み検証はHEAD・依存・入力・条件の一致を確認して再利用する。
- 権限と安全Gateが成立する作業branchの通常commit/push、Draft PR作成・更新・解除、
  低リスクmain mergeと事後CI確認は自律実行する。force/direct main push、保護bypass、無断branch削除は禁止。
- main mergeはP0/P1未解決0、全必須CI成功、最新HEAD/base一致、競合・未解決レビューなし、
  保護遵守、未承認の外部副作用なし、高リスク変更なし、互換性維持をすべて要求する。
- 再現可能な不具合は根本原因・最小修正・回帰検証で解消して再開する。
  約3つの異なる修正案で解消しない、影響が拡大する、P0/困難なP1・証跡不整合は停止する。
- 実AWS接続・State読取りも承認されたAccount/Region/資源/目的に限定する。
  Terraform Apply、State変更、重要IAM変更、配備/Enablement、有料OpenAI、破壊的・不可逆操作、
  重大セキュリティ変更、課金上限を保証できない操作は具体的な明示承認を得る。
- 高リスク工程の承認は事前Gate・対象hash・回数/費用・本処理・事後検証・証跡・必要なClosureを一括する。
  承認内の軽微な判断で再承認を求めない。partial failure/結果不明/Closure失敗は成功扱いせず停止する。
- Coaching V2の30点採点/深掘り、V1互換、STAR Ver.1.4、本人分離/冪等性/Recovery、
  Session/Attempt/Evaluation、Git/worktree、Plan/State/journal/private ledger/監査証跡を保持する。
  sandbox・承認ポリシーを緩和しない。Bootstrap復旧承認をApply/STAR配備/OpenAIへ拡大しない。
