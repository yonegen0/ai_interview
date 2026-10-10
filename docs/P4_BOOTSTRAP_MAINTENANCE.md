# Canonical bootstrap S3 State保守

`bootstrap_maintenance.py`は既存canonical bootstrap Stateに対するplan/deployのexact dev `s3:GetObjectVersion`追加専用実行器。初期構築器・移行adapter・Terraform資源addressを変更せず、new moduleも作らない。新コードの存在、inspect成功、CI成功は正式Plan/Applyの承認ではない。

## 採用した構成

- 別実行器: 初期構築器に分岐を追加するとlocal binding・migration journalと更新運用が混在するため採用しない。
- 新規private run: 承認Git revisionの5つのbootstrap `.tf`とprovider lockをGit blobからbyte-for-byteコピーする。source/コピー先の一覧・hashを結合し、余分な構成、tfvars autoload、local State、symlink/junctionを拒否する。
- 保守専用`backend.tf`: 空のS3 backend宣言を追加。hash固定private HCLはcanonical bootstrap key、Account、Tokyo、encrypt=true、use_lockfile=trueのみ。profile/token/credentialは含めない。
- `TF_DATA_DIR`とdefault workspaceを新規runへ固定。明示短期認証をchildだけへ渡し、空AWS configと固定Terraform CLI configで暗黙のendpoint/provider overrideを排除する。
- `init -reconfigure -input=false -lockfile=readonly -lock=true -lock-timeout=0s`: 新規ディレクトリに旧Stateや旧backend metadataを持ち込まない。`-reconfigure`はState migrationを行わない。[Terraform 1.14 init](https://developer.hashicorp.com/terraform/cli/v1.14.x/commands/init)。

`maintenance_contract.py`は入力・承認・全差分・適用後Stateの純粋検証、`maintenance_aws.py`はSDK write禁止とAWS読戻しを担当する。公開`terraform/bootstrap/main.tf`へS3 backendを追加して初期構築経路を変える方式は採用しない。

## Stateと承認の境界

canonical先は`ai-interview-state-<Account>-ap-northeast-1/bootstrap/terraform.tfstate`、default workspace。名前/serial/件数だけで採用せず、hash固定のcanonical identity adoptionと成功読戻しreceiptからlineage/serial/VersionId/SHAを固定する。新しいdescriptorのidentityはその証跡と一致する必要がある。

S3 `ExpectedBucketOwner`、Region、Versioning、AES256、VersionId指定Get、bytes SHA、head再照合、version/delete-marker inventory、全32 managed address、active lockを確認する。不明/403を不存在扱いしない。許可済みexact prefixの完全paginationでlock不存在を証明し、拒否/不完全/token循環では停止する。[S3 GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)、[HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)。

32資源のIAM policy/trust/role ID/boundary/tags、CI Roleのinline/attached policy集合、OIDC、SES identity、bucketのhardened属性をread-only確認する。提案statementのsimulationは実IAM適用の証明ではない。[IAM simulationの制約](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)。

この実行器はcanonical baseline serial 1、既存32資源、State-owned OIDC provider、email SES identity、WIF=falseの今回の修正に限定する。別baseline・後続の別保守には新たな実装/レビューが必要。State-owned providerを保持する入力は`oidc_provider_arn=""`。external ARNへの変更は拒否する。

入力はTerraform var-fileと同じ8項目。private descriptorが入力ファイルhash、provider lock hash、source SHA、実行principal Role ARN、backend、State identity、sorted address一覧、adoption/receiptのpath/hashを固定する。descriptorはschema 1、期限24時間以内、approvedの実booleanを要求する。未知field、hidden TF/AWS endpoint環境、clean main/remote mainの不一致を拒否する。

Plan descriptorのkindは`p4-bootstrap-maintenance-plan`。approved=trueでも、normal_lockfile_writes_approved=true、canonical_state_writes_approved=false、iam_policy_updates_approved=falseが必要。費用枠は別承認の`cost_cap_usd="0.05"`。candidate approved=falseはinspect専用で書込み承認を意味しない。

Apply descriptorはkind=`p4-bootstrap-maintenance-apply`。同じsource/State/入力/実行主体を固定し、run絶対path、実plan SHA、binding SHA、元Plan承認SHAを追加する。Applyに伴う正常State書込みと2 policy更新はこの別descriptorで明示承認する。Plan承認を転用しない。

## inspect / Plan / Apply

以下は将来の承認対象コマンドの表示例。repositoryはcleanな指定revisionのcheckout、private pathはそのGit common-dirの親にある`.p4-artifacts`内。Worktreeも同じprivate領域を使用する。

```powershell
# 読取り専用。descriptorはapproved=falseでもよい。毎回新規の証跡directory。
backend/.venv/Scripts/python.exe backend/skills/p4/bootstrap_maintenance.py inspect --approval <private-plan-descriptor> --approval-sha256 <descriptor-SHA256> --directory <new-private-inspection-directory>

# 別途Plan承認が必要。許可されたsingle operator端末だけで実行。
$env:P4_BOOTSTRAP_MAINTENANCE_EXECUTION_READY = 'true'
backend/.venv/Scripts/python.exe backend/skills/p4/bootstrap_maintenance.py plan --approval <approved-private-plan-descriptor> --approval-sha256 <descriptor-SHA256> --directory <new-private-run>

# 生成物の全差分と実SHAをレビューした後の別承認が必要。
backend/.venv/Scripts/python.exe backend/skills/p4/bootstrap_maintenance.py apply --approval <approved-private-apply-descriptor> --approval-sha256 <apply-descriptor-SHA256> --directory <same-private-run>
```

inspectはTerraform version/init/plan/applyを呼ばず、AWS SDKはGet/Head/List/Describe/Simulateだけを許す。実行主体をSTS AccountとIAM Role ARNで照合し、State versioned Getとexact lock lifecycleの権限をsimulationする。

Planは正常local operation lockを取得し再照合、state namespaceごとの永続ledgerへ開始記録をexclusive/fsync保存する。isolated backend初期化後にmetadata/default workspace/`state pull`を照合し、State identity/version inventory不変を確認してから、通常locking付き`plan -out`を1回実行する。`show -json`の全32資源、prior/planned values、全入力、出力、unknown/drift/deferred/checksを監査する。

許容差分は2 policyの指定statement追加だけ。その他30資源no-op、create/replace/destroy=0。無関係fieldや権限拡張、trust/boundary/OIDC/WIF/S3/runtime変更を拒否する。**実Plan未実行の時点で2 updateを確定したとは扱わない**。

Plan後にState identity、versions、lock、実AWS、コピー構成を再確認し、saved Plan bytesのSHA256・review SHA・source/入力/backend/provider lock・State identityをbindingへ結合する。成功時はApply承認待ちで終了する。[Terraform saved Plan](https://developer.hashicorp.com/terraform/cli/v1.14.x/commands/plan)。

Applyは既存runのplan/binding/review/inputをhash照合し、同じ全差分を再監査する。最新State・version inventory・AWS実体を`state pull`とApply直前にも再確認する。通常locking付きsaved Plan Apply前に永続apply-startedをexclusive保存し、再実行を禁止する。適用後はlineage維持・serial前進・全address/ID・出力・2 policy以外の不変・IAM実体・lock不在を確認して完了を記録する。

## 禁止操作と失敗時

state push/rm/import/surgery、初回bootstrap plan/replan、旧Stateコピー、migration/force-copy、force-unlock、lock=false、destroy、saved Plan以外のApply、State外の変更、再Plan/再Apply/ledger削除は提供しない。Stateが見えない・空・別identity・lockありなら開始しない。[S3 native locking](https://developer.hashicorp.com/terraform/language/v1.14.x/backend/s3)。

失敗/timeout/結果不明はprivateログ・開始journal・途中saved Planを保全して停止する。AWS headの読取り診断だけを行い、lockを削除しない。実行を別directoryや別descriptorに替えても同じcanonical namespaceの開始ledgerが再Planを拒否する。成功後のApplyも1回のみ。ledgerは単一指定端末の排他/履歴であり、複数clone・複数端末で並行実行してはいけない。

Windowsのprivate directoryは敏感なbytesを書込む前にcurrent user/SYSTEM/AdministratorsだけへACL制限し検証する。POSIXはdirectory 0700/file 0600。stdoutには固定status、count、承認対象plan SHAだけ。raw State/plan/policy/email/credentialをCI artifact・ログ・チャットへ出さない。

## 承認・費用・検証範囲

必要な承認はこのbranchのexact HEAD/base main merge、その後新mainと実環境を再固定した正式Planのみ、最後に実saved Plan SHA指定Apply。今回のコード/テスト/通常Push/Draft PRにはAWS書込み・main merge・正式Plan/Applyの承認を含めない。

Planの将来AWS書込みはnormal `bootstrap/terraform.tfstate.tflock` Put/Deleteのみ。backend initを含むcycle回数は固定1回としない。canonical StateのPut/Delete、IAM変更、Artifact uploadをPlan承認へ含めない。State version増加を検出したら失敗として止まる。外部の無承認操作までコードで防止する仕組みではないので、既存runbookのsingle operator/単一端末条件も守る。

2026-10-10の公式Price Listに基づく保守モデルは5,000 requestをTier1で計上、64MiB egress、64KiB lock versionの1か月保存で税別0.030626526 USD。費用枠案0.05 USD+税は未承認。実請求未確定で、IAM/GitHub billingはAWS S3モデルと別に扱う。[S3料金](https://aws.amazon.com/s3/pricing/)。

AWS/CLI正常経路は合成State・mockで検証する。live `inspect`は正式Planの成功やIAM適用を証明しない。正式init/Plan/Applyは別承認まで未実行。新mainのSHAはmerge後に変わるため、source bindingとdescriptorを再生成する。cold Gate FAIL、実AI30人未検証、AWS受入未完了は継続し、公開準備完了とは判定しない。
