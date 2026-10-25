# Terraform・AWS Infrastructure 開発規約

## 適用範囲・正本

- `terraform/` に適用。`.github/workflows/` のTerraform・IAM・OIDC・AWS配備変更にも本規約を参照する。
- [ルート安全規約](../AGENTS.md)・[自律実行ルール](../docs/CODEX_AUTONOMY_RULES.md)を優先する。
- 正本は各root moduleの `required_version`・`required_providers` と `.terraform.lock.hcl`。現行はTerraform `= 1.14.9`、AWS Provider 6系。
- 現行lock版はBootstrap/TestがAWS Provider 6.64.0、devが6.65.0。差異を自己判断で統一しない。
- 詳細実行手順は [P4 Terraform Runbook](../docs/P4_TERRAFORM_RUNBOOK.md) と既存の承認・監査文書を参照する。
- ここに書かれた規約は`init`・`plan`・`apply`・AWS操作の実行承認ではない。

## 構成とHCL

- `bootstrap/`：State・Artifact用Bucket、GitHub OIDC、CI IAM/Boundary等の独立管理境界。
- `environments/dev/`：閉鎖状態を基本とするサービス環境と限定検証用設定。
- `environments/test/`：テスト専用の設定・Closure前提・検証条件。
- `modules/service/`：API Gateway、Lambda、DynamoDB、SQS、Scheduler、CloudWatch等の再利用構成。
- Resource/variable/output/module名は既存のsnake_case・既存名を優先し、参照を壊すrenameを避ける。
- HCLは `terraform fmt` に従い、変更範囲以外を一括整形しない。
- 入力型・`validation`・`sensitive`、output公開範囲、provider設定の既存制約を守る。
- 依存の追加・Provider版更新・Stateのresource address変更は別途影響と承認を評価する。
- Module化は実際の再利用・責務の境界に必要な場合だけ行い、無目的な抽象化をしない。

## AWS・セキュリティ・費用

- 完全サーバーレス・AWS無料枠優先・低固定費を維持し、常時稼働課金を安易に追加しない。
- 対象Account/Region、GitHub OIDC Subject、Role、Boundary、最小権限を現行設定と照合する。
- IAMの `*`・追加アクション・信頼ポリシー・権限境界変更は特に厳密にレビューする。
- DynamoDB/SQS/S3/Cognito/CloudWatchの認証・暗号化・ログ保管・アクセス分離を維持する。
- State、Plan、tfvars、backend設定、Secrets、Account識別子、private証跡を公開Artifactへ含めない。
- `.terraform` metadata、State、lock、Workspace、private Ledgerを壊さず、無断上書きしない。
- BackendのS3 Versioning、暗号化、State lockingの既存方式を変更しない。
- CloudWatch監視・アラート・Recovery・Closureを配備の付帯条件として扱う。
- 予算見積り・アラートはAWS請求を強制遮断するhard capとはみなさない。

## 検証と副作用の区別

- `terraform fmt -check` はオフライン整形検査（対象dirと未使用の変化を確認）。
- `terraform validate` はProviderや初期化済み作業領域を要する場合があるため、既存のオフライン手順を使用する。
- `Offline Mock`・静的チェックは実AWSの構成/権限/課金/State整合を保証しない。
- `terraform init` はProvider/Module取得、backend設定・状態移行・ローカルmetadata変更を起こし得る。
- `terraform plan` はAWS/Stateへの読取りやrefresh、lock取得等の副作用があり、単なる静的検査ではない。
- `terraform apply`・Stateのimport/move/remove/migration・実配備は高リスクの個別承認対象。
- 実AWS E2E、IAM実効権限、実Bedrock、閉鎖読戻しはローカル検証と別に記録する。
- `init`/`plan`を含め、接続先と実行条件が未確認なら自己判断で実行しない。

## Plan・Apply・Closure

- PlanとApplyは別の承認境界。正式saved Planだけを監査し、対象SHA・HEAD・入力・State/lockを照合する。
- 消費済み・期限切れ承認、別namespace、古いsaved Planを再利用しない。
- fail-closedを維持し、差分不明・State不整合・lock・部分失敗・結果不明では未承認の再実行をしない。
- P4一時Enablement・条件付き自動Closureの詳細条件は[承認テンプレート](../docs/P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)とRunbookを参照する。
- 成功・失敗時とも証跡を保全し、Apply・Closure・State読戻しの事実とMock結果を混同しない。
- GitHub ActionsのPlan・Deploy Workflowで権限・OIDC・環境保護・副作用範囲を無断変更しない。
- mainへの反映は保護Ruleset、必須CI、Head/base一致、レビュー条件を守る。

## 公式ドキュメント

- 対象Terraform 1.14系・AWS Provider 6系に対応する公式仕様を先に確認する。
- Terraform Language: https://developer.hashicorp.com/terraform/language/v1.14.x
- CLI init/plan: https://developer.hashicorp.com/terraform/cli/commands/init ｜ https://developer.hashicorp.com/terraform/cli/commands/plan
- Terraform S3 Backend: https://developer.hashicorp.com/terraform/language/v1.14.x/backend/s3
- AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs （採用版はlockfile優先）
- AWS Well-Architected: https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- IAM: https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html
- GitHub Actions OIDC: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- 外部仕様に関わる変更時だけ必要な公式資料を調べ、確認不可は未確認と記録する。
