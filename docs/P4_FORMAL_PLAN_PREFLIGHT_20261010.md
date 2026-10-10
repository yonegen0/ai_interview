# P4 正式Terraform Plan 事前監査 — 2026-10-10 JST

**P4_FORMAL_PLAN_BLOCKED_SECURITY_REVIEW_REQUIRED**

承認不要の監査・修正・オフライン検証を実施した。実機のplan/deploy Roleにはcanonical dev Stateの`GetObjectVersion`許可が不足している。正式Planは実行しない。変更は`codex/p4-formal-plan-security-20261010`に隔離し、main merge・IAM実変更・AWS書込みは別承認まで停止する。

## 1. 確定済み対象と実機監査

| 項目 | 結果 |
| --- | --- |
| Repository / 現main | `yonegen0/ai_interview` / `339700d50eddf3841443b217329d21c8e4a1f1a3`。remoteと一致 |
| main CI | Backend `37951416972`、Frontend `37951417081`、P4 `37951417139`は成功。upload Run `38009002544` / Attempt 1も成功 |
| Artifact | `19044650` bytes / SHA256 `3f44f2a67a7323dcd8522d1ef128cde7a9258038946d5c7a5c13064c51a83b42` |
| Artifact VersionId | `dDtENLLmAcrHx_k3o8cr.Cduvk.Z_cni` |
| Bucket / Key | `ai-interview-artifacts-835384817629-ap-northeast-1` / `lambda/339700d50eddf3841443b217329d21c8e4a1f1a3/38009002544/1/app.zip` |
| Account / Region | `835384817629` / `ap-northeast-1`、既存SSO/STS照合成功 |
| dev State | serial 12 / managed 61資源 / schema 3。lineage・VersionId・SHAは既存成功証跡と一致 |
| closed確認 | API停止、Worker/Streams mapping Disabled、Scheduler DISABLED、validation Alarm 0、active lockなし、監査対象State外dev資源0 |
| bootstrap State | canonical採用lineage一致、serial 1 / 32資源、VersionId固定読戻し成功、lockなし。State内IAM policyと実機が一致 |
| CI Role全policy | plan 3 / deploy 5 / test 6 / artifact 1、全inline/attached/default versionを読取り。4 Roleともpermissions boundaryなし |
| runtime boundary | 4 runtime Roleへの既存boundary付与と実policyを読取り確認。変更しない |
| SCP / RCP | Account→rootを取得、両policy typeともattach 0。対象はOrganizations管理Account。SCPは管理AccountのRoleを制限しない |
| State/Artifact bucket | owner/Region、Versioning Enabled、AES256、BucketOwnerEnforced、Public Access Block全true。policyは非TLS通信拒否のみ |
| OIDC | 全4 Roleのtrustは既存承認descriptorのexact subject/audience/providerと一致。OIDC provider設定を取得確認。今回CI Roleのassumeは行っていない |
| Artifact読戻し | local ZIP・既存VersionId指定Getの保存ZIP・再現ZIPの実SHA一致。今回VersionId指定Headのsize/checksum/AES256/metadataも照合 |
| Manifest / Provenance / Descriptor | 実SHAはそれぞれ `785f1447e4034a9cfd3bfab5294a63cb73b01419d3bf91dad2452a2fbf15f243` / `cc8dc440b252bbaf851c8d500a97b81729ca18203a282c806d1148846ff170b5` / `f536a7177a03f306a9498f7c11f861b5ff6b8a8da36d531ed2400a06ac931b89`、不変 |
| GitHub正式Plan変数 | repository/dev Environmentとも `AWS_DEV_ACCOUNT_ID`、`P4_OIDC_SUBJECT`、`P4_DEPLOY_INPUTS`、`P4_AWS_EXECUTION_READY`未設定。ownerは個人Userのpublic repositoryでorg共有変数は非該当。dev Environmentへ明示設定する承認が必要 |

VersionId付きGetObjectは`GetObjectVersion`を必要とする。[AWS GetObject仕様](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)。不存在HeadObjectはListBucket許可がなければ403となり得る。[AWS HeadObject仕様](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)。SCPの管理Account除外は[AWS Organizations仕様](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)による。

## 2. IAM最小修正と安全なlock判定

実機IAM simulationはplan/deployともcanonical Stateの`GetObjectVersion=implicitDeny`、lockのGetObject=allowed、prefix未指定ListBucket=implicitDenyだった。bucket policyはRoleに追加Allowを与えず、既存全policyにも当該Version読取りAllowがないため、権限不足を確認した。

Terraform修正はplan/deployの`state-and-artifacts`に次の1 statementを追加するだけ。test/artifact Role、trust、runtime boundary、backend/provider、既存write権限を変更しない。

```json
{
  "Sid": "DevVersionedStateRead",
  "Effect": "Allow",
  "Action": ["s3:GetObjectVersion"],
  "Resource": ["arn:aws:s3:::ai-interview-state-835384817629-ap-northeast-1/dev/terraform.tfstate"]
}
```

lock Headの403を不存在とみなさない。既存`dev/*`のListBucket許可でexact lock keyをPrefixに指定し、全pageを読み、exact keyが存在しないことを証明する。存在、権限拒否、不完全応答、不正/循環tokenは停止。State VersionId固定Get、AES256、head再照合、lineage/serial/hash/namespace検証は維持する。広いbucket一覧権限は追加しない。

提案statementを一時的なsimulation入力へ渡すread-only検証では、canonical GetObjectVersionとexact lock prefixのListBucketはallowed。これはIAM実変更ではなく、CI Roleによる実S3要求成功の証明でもない。[IAM simulatorの制約](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)。適用後の正式経路では、最初のS3 upload前に実plan RoleでStateを読む。

Terraform 1.14.9のdefault workspaceは、既定`env:/`一覧のAccessDeniedでdefaultのみへ戻るため、その一覧権限を追加しない。[当該versionのbackend実装](https://github.com/hashicorp/terraform/blob/v1.14.9/internal/backend/remote-state/s3/backend_state.go)。backendとworkspace設定は維持する。

## 3. A/B比較と採用案

**現在の正式Planには、修正したA経路を推奨する。Aの採用と追加書込みはまだ未承認。Bは将来の改修候補であり、今回実装していない。**

| 比較 | A: 既存Plan経路を安全化し、再build/uploadを個別承認 | B: 既存Artifact再利用経路を新設 |
| --- | --- | --- |
| source/Artifact結合 | clean/current main、同一workflow SHAでbuild。新しい明示承認ZIP SHA inputと実ZIP・build manifestのdigest fieldを照合してからPut。現Artifactと同じbytesを要求できるが、新Key/VersionIdとなる | Artifact source339700…と変更後workflow SHAを別々に固定し、祖先関係だけでなく全app blob・lock・build入力・metadata/provenanceを照合する契約が必要 |
| 再現性 | 既存Linux3.14/locked dependency buildを継続。実SHAが承認値と違えばupload前に停止 | 既存VersionIdのbytes読戻し＋承認済み再現証跡/独立再build照合を設計する必要 |
| State整合 | 実plan Roleのversioned State読取りをbuild前/最初のPut前に追加。変更なら0Put。既存Plan前後State照合を維持 | 同じState/lock保証が必要。Artifact再利用だけでは整合性は改善しない |
| CI identity | 既存main/dev/OIDC境界を保持 | source/workflow二重revisionのOIDC/Run/envelope/Apply結合を新設する必要 |
| saved plan | 既存plan hash、inputs hash、lock hash、code SHA、State identity、VersionId binding、durable Apply journalを維持。envelopeは最後 | Apply側の現在の`lambda/current-sha/plan-run/attempt/app.zip`検査も改修しなければ利用不能 |
| 工数/リスク | 既存契約を維持する小修正。State事前確認・transport読戻し・承認SHAの回帰試験を追加 | 新descriptor/schema、source移行規則、workflow/driver/Applyを横断する追加開発・レビューが必要 |
| AWS費用 | ZIP再保存1version分の約0.000443 USD/月と1Putが増える。Plan側ファイル5件はどちらも必要 | ZIP再保存を省略できる。既存ZIPの検証Getは必要なので外向き読戻し費用は残る |
| 運用負荷 | Plan/Applyの現行のsame-main契約と単一build手順を維持 | 成熟後は再buildの負荷を減らせるが、旧sourceと新workflowの互換性証明を毎回維持する必要 |
| main変更/再upload | 今回修正のmergeには別承認。merge後のmainを新package sourceとし、新manifest/provenanceをローカル再固定する。正式Plan時の追加ZIP uploadは別承認 | CI修正をmergeする必要。app/lock/build inputs同一を厳密に証明できれば旧Artifactを保てる設計は可能。inputsが変わればArtifact再作成・再uploadが必要 |

A経路の実装を追加安全化した。S3 clientはSDK再試行なし、ExpectedBucketOwner、IfNoneMatch=*、AES256、SHA256 checksum。各Putの返却VersionIdを指定Getし、size/encryption/hashを照合してから次のPutへ進む。承認SHA付きZIPが必要で、未指定/不一致なら書込み前に停止。Plan関連objectは1件10MiB以下。saved plan/JSONはCIの公開artifactやログに出力しない。

既存VersionIdをそのまま正式Planに用いる要求の場合、Aでは満たせない。その場合はBの実装・レビュー・mergeを完了してから別承認する。A選択による新Key/VersionIdへの切替を、現upload承認から推測して実行しない。

## 4. 19項目とschema対応

**候補19項目をそのまま入力JSONへ渡すと拒否される。** CI設定は10項目、terraform_devのUSD入力は14項目。3項目が検証済みAccount/Regionと固定CORSから派生し、残る2項目はTerraform defaultとなる。この17+2の全19実効値が既存candidateと一致した。

| # | Terraform変数 | 実入力/供給方法 | 検証結果 |
| --- | --- | --- | --- |
| 1 | account_id | AWS_DEV_ACCOUNT_ID + STS/Account guard、直接JSON入力不可 | 対象Account一致 |
| 2 | region | workflow/AWS_REGIONのTokyo、直接JSON入力不可 | ap-northeast-1一致 |
| 3 | boundary_arn | P4_DEPLOY_INPUTS / terraform_dev | 既存runtime boundary一致 |
| 4 | ses_email | P4_DEPLOY_INPUTS / terraform_dev | 既存送信元保持、private値は非表示 |
| 5 | ses_identity_arn | P4_DEPLOY_INPUTS / terraform_dev | Account/Region/identity一致、private値は非表示 |
| 6 | alarm_email | P4_DEPLOY_INPUTS / terraform_dev | SNS email通知先保持、private値は非表示 |
| 7 | cors_origins | terraform_dev固定localhost:3000 | baseline一致。変更する場合は別schema改修が必要 |
| 8 | monthly_budget_usd | USD文字列10.00→Terraform number | 正値・小数2桁・baseline一致。JPY modeとの混在禁止 |
| 9 | log_usage | P4_DEPLOY_INPUTS: customer | 14日。現Stateの5ログは7日なので延長、短縮なし |
| 10 | api_enabled | P4_DEPLOY_INPUTS | false、closed保持 |
| 11 | worker_enabled | P4_DEPLOY_INPUTS | false、closed保持 |
| 12 | streams_enabled | P4_DEPLOY_INPUTS | false、closed保持 |
| 13 | scheduler_enabled | P4_DEPLOY_INPUTS | false、closed保持 |
| 14 | artifact_bucket | Aではdriverが追加 / terraform_devは直接tuple受付 | 対象bucket固定 |
| 15 | artifact_key | Aでは実Plan Run/Attemptで新Keyを生成 | 現候補旧Keyのshape/receipt一致。Aの新Keyは未発行 |
| 16 | artifact_version | Aでは新Put返却VersionIdを追加 | 現候補dDt…は検証済み。Aでは新VersionIdへ切替の承認が必要 |
| 17 | artifact_sha256_base64 | Aでは実ZIP digestを追加 | 承認ZIPのBase64と一致を必須化 |
| 18 | worker_ai_environment | Terraform default {}、両Python schema受付外 | baseline/default空map一致、実AI呼出しなし |
| 19 | worker_wif_enabled | Terraform default false、両Python schema受付外 | false一致、IAM WIF変更なし |

backendは19 resource変数とは別境界。既存`ai-interview-state-835384817629-ap-northeast-1`、`dev/terraform.tfstate`、default workspace、encrypt=true、use_lockfile=true、allowed_account_ids、Terraform1.14.9、4 provider lockを維持。State identityも入力claimから採用せず、VersionId指定実読戻しで固定する。

retention短縮が実saved planに現れた場合は、既存State-bound承認・incident/support/audit証跡保全ルールを適用し、未承認なら停止。customer→developerやunknown/new log groupへの緩和は行わない。

## 5. 書込み・lock・費用の承認範囲

| A経路の将来書込み | 成功時の回数 / 条件 |
| --- | --- |
| `lambda/<NEW_MAIN_SHA>/<REAL_PLAN_RUN_ID>/1/app.zip` | 1 Put / 返却VersionId指定Get 1。新main sourceと承認ZIP SHAに結合 |
| `plans/<REAL_PLAN_RUN_ID>/1/dev.tfplan` | 1 Put / VersionId指定Get 1、最大10MiB |
| 同prefix `plan.json` | 1 Put / VersionId指定Get 1、最大10MiB |
| 同prefix `summary.json` | 1 Put / VersionId指定Get 1、最大10MiB |
| 同prefix `review.private.json` | 1 Put / VersionId指定Get 1、最大10MiB、private内容 |
| 同prefix `envelope.json` | 全先行検証後に最後の1 Put / VersionId指定Get 1、最大10MiB |
| `dev/terraform.tfstate.tflock` | 通常S3 backendのlock Put/Delete。Terraform initでmodule stateの再構築に伴うlock、plan refreshのlockなど回数はbackendの実経路に依存し、固定1cycleとは断定しない |
| canonical dev State | Plan中のState Put/Deleteは許可しない。既存Stateを保つ。State version数増加や不変条件逸脱なら停止 |

S3 backendの正常なlockfile操作は[HashiCorp S3 backend仕様](https://developer.hashicorp.com/terraform/language/backend/s3)による。`-lock=false`、force-unlock、既存lock削除、手動State修復は禁止。active lockがあれば開始しない。後続のTerraform Applyは別承認。

当日Price List: Tokyo Standard storage 0.025 USD/GB-month、Tier1 0.0000047 USD/request、Tier2 0.00000037 USD/request、external egress 0.114 USD/GB。[S3料金](https://aws.amazon.com/s3/pricing/)。無料枠・既存dev baselineを算入しない保守的見積り。sidecar各10MiB上限、6Put/6Get、通常lock/再監査reserveを含む。

| 費用範囲 | USD、税別 |
| --- | ---: |
| 既存Artifact upload作業の初月見積り | 0.008688225 |
| 今回preflightの保守的監査reserve | 0.002598837 |
| 今回までの累計モデル | **0.011287062** |
| 正式A Planの追加上限モデル | **0.014231770** |
| Aを1回実行した場合の初月累計モデル | **0.025518831** |
| 次回承認で提案する余裕込み費用枠 | **0.05 USD + 税**、未承認 |

実請求額は未確定。これは500/1000 requestを高いTier1で過大計上するreserveであり、実際の課金額や旧upload承認0.01の違反を断定するものではない。ただし今後の正式Plan・監査まで旧0.01枠に含めることはできない。Cost Explorer有料APIは呼出していない。GitHub hosted runner billingはAWS費用に含めず、accountの無料枠/契約に別途依存する。

## 6. 実施済み検証と停止条件

独立worktreeでTerraform validate 4root、mock provider 50件、IAM inline quota/最小scope試験をPASS。ローカルBackend全offline回帰1362件（57 AWS試験除外）と、最後のapproved ZIP digest/失敗時0Put/再Put禁止等を含む関連114件をPASS。最終branch SHAに対するGitHub Backend/Frontend/P4 CIをpush後に確認し、private証跡へ保存する。package/production code/uv.lock/build_lambda/4 provider lockは現mainから不変。

以下は正式Planの前提不一致として停止する。

- Account/Region/main/workflow/CI/environment/trust/boundaryの不一致、実plan RoleのVersionId Get拒否。
- approved SHA未指定、再build ZIP hash/manifest digest不一致、既存Artifactの無断置換。
- canonical Stateのlineage/serial/VersionId/hash変更、lock、State外dev資源、closed逸脱。
- 10項目CI設定/14項目tool入力の不一致、4flags true、CORS/default AI設定の不一致、retention短縮承認不足。
- Put/Get失敗、409/412、timeout/結果不明、VersionId/size/encryption/hash読戻し不一致、sidecar上限・費用枠超過。
- 全saved plan監査で未承認のcreate/replace/destroy、IAM/runtime/architecture/backend/provider/Concurrency変更を発見。

partial upload/Plan failure後は再dispatch/rerun/再Put/marker削除/S3削除/手動State修復をせず、read-onlyで診断する。saved plan成功後もApply承認までは停止する。今回のコード/試験の存在はAWS writeやPlanを承認した証拠ではない。

## 7. 必要な明示承認の順序

1. 修正branchのレビューとexact HEAD/base指定によるmain merge。今回未実行。
2. **bootstrap正式saved Planの作成のみ**。採用済みcanonical bootstrap State・入力・provider lockを固定し、normal backend lock操作/費用を明示。旧local State・空State・初回bootstrap/migration経路を流用しない。想定差分はplan/deployのstate policy各1 update、create/replace/delete=0、その他no-op。実saved plan全件監査とSHAを報告する。
3. その**bootstrap saved plan SHA指定の1回Apply**。IAM更新2件を別承認し、失敗時read-only停止。適用後policy/State/lock、実plan Roleのversioned読戻しを再確認する。
4. A方式の採用、追加ZIP/sidecar6Put、承認ZIP SHA、新main/source SHA、new manifest/provenance、Plan用GitHub dev変数、必要lock操作と費用枠を含む**dev正式Plan作成のみ**の承認。
5. 実saved planの全差分・State identity・Artifact tuple・plan SHAを審査した後の**dev Apply別承認**。

旧upload descriptorのapproved=trueはArtifact uploadだけの承認であり、Plan/IAM/Applyへ転用しない。今回新規proposalはapproved=false。Enablement/Closure、実AI、公開判定は含めない。cold Gate FAILと実AI30人未検証、AWS受入未完了は継続する。

private保存先: `.p4-artifacts/formal-plan-preflight-20261010/`。current user/SYSTEM/Administrators限定ACL。Windows既存13ファイルと旧private証跡を保護し、新proofのみ追加。private descriptor/State/policy/メール/通知先/tokenはGitへstage/commit/pushせず、本文も報告しない。