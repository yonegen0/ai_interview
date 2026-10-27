# Gate B Plan001/002・State互換性監査（2026-10-27 JST）

判定: **ROOT_CAUSE_UNKNOWN_EVIDENCE_REQUIRED / NOT_READY**。
State互換性の異常は再現しなかった。Plan002はTerraform init/planより前の
live/readiness照合区間で失敗した。直接の拒否条件は既存journalでは失われており、
新しいPlan承認を最終化・実行しない。現在のjob tokenによるEnvironment変数APIの
HTTP403はAWS不使用の真正CIで再現したが、当時の直接原因とは区別する。

## 証拠と判定

| 対象 | 判定 | 証拠・限界 |
| --- | --- | --- |
| Plan001 / Run40482570308 Attempt1 | PROBABLE: Secret搬送時の末尾CR/LF除去による承認hash不一致 | 固定descriptorにLFがあり、gh 2.102.0実装と同じ変換で`PlanApprovalHashMismatch`を再現。実Runの具体的な拒否コードは未保存。journal暗号化も失敗 |
| Plan002 / Run40485301364 Attempt1 | CONFIRMED: pre-initのlive/readiness区間で停止。詳細根因UNKNOWN | 本人鍵で認証付きCMS復号exit0、projection exit0、生成平文cleanup成功。承認/run-bound、STS response/caller identity、State読取り、CLI version exit0を観測。最後のSDK開始記録はAPI Gateway v2、その後DeploymentError/ExternalOrScopeFailure。init/plan開始記録なし |
| Plan002の具体的な候補 | PROBABLE: Environment変数読取りの権限不整合。当該権限不足の現在の再現はCONFIRMED | Stage照合後に両Environmentのvariables APIをjob tokenで読むコード。公式APIはEnvironments(read)を要求するが、workflowのtoken権限に当該選択肢がない。後述の真正CIでは両APIが403。実RunのHTTP403やStage応答内容は記録されず、当時の直接原因は確定としない |
| Terraform State互換性 | CONFIRMED: 保全済み12/13の現行CLI/Providerによるschema照合・読込み成功 | 後述のオフライン検証。remote backendやProvider Configure/Refreshを検証した意味ではない |
| Stage残差分 | 既存証拠で確認済み。発生原因UNKNOWN | State13は6ログ項目、既存AWS GetStage証拠は4項目。欠落はrequestTimeEpoch/responseLatency。保存応答のDestinationArn・FormatはPlan002承認のbeforeと一致。ただしPlan002実行時のStage応答は保存されていない |
| 元Apply / Run40336463379 Attempt1 | Workflow FAILURE、Terraform正常終了・直接原因UNKNOWN | source92e0aa2、2026-10-26 23:05:57–23:09:15 JST。State更新や32対象一致からApply正常終了を推定しない |

Plan001とPlan002は同じworkflow stepが失敗したが、同じ内部フェーズとは立証できない。
Plan002は初期承認照合より先へ進んだため、Plan001のhash不一致を流用して説明しない。
API開始記録はそのAPIの成功記録ではない。最後のSDK応答の成功も独立には断定しない。

## State・バージョン履歴

| 時点 | CLI | dev AWS Provider | 根拠 |
| --- | --- | --- | --- |
| 2026-09-15 / 281c478 | required_version =1.14.9 | lock6.64.0 | dev main.tf/lockの初回追跡履歴 |
| 2026-09-18 / 824dc5d | =1.14.9を維持 | lock6.65.0へ変更 | lock差分 |
| 2026-10-16 / 72b482d | =1.14.9を維持 | 6.65.0を維持 | lockのplatform hash追加。版変更ではない |
| 2026-10-26元Apply前後 | State12/13ともwriter1.14.9 | source92e0aa2のlockは6.65.0 | 同じlineage、serial12→13。State自身からProviderの正確なwriter版は断定しない |
| Plan001/002・調査時main59e76ab | CLI pin1.14.9 | lock6.65.0 | workflow/root/lock一致 |
| PR43候補 | 1.16.7/1.17.0の資格検証は別工程 | 候補6.70.0 | Draft/HOLD。mainへの採用証拠なし。本監査で変更しない |

serial12→13は元Apply前後に保全された同lineageのsnapshot間で観測した。
正確なState write時刻は本監査では特定していない。State13が書かれたことは
Apply全体の正常終了やAWS実体との一致を意味しない。

## オフライン実測

本人限定DACLの新規作業領域で既存snapshotを読み、原本hashの不変を確認した。
State12は34resource blocks/61instances、State13は41blocks/77instances。
State形式version4、writer1.14.9、Provider参照はhashicorp/aws、outputはmanifest。
State13全77instancesに識別子があり、output manifestは保存manifestと一致。
4 Lambdaすべてのbucket/key/object version/source_code_hash/publish versionがmanifestと対応。
実AWS LambdaやS3への新規照会はしていない。

既存のWindows CLI1.14.9とProvider6.65.0を専用領域へ配置し、backend/resource設定を持たない
最小configurationで`providers schema -json`、ローカルStateコピーへの`show -json`を実行した。
State12/13の全resource typeで保存schema_versionと現在schema versionが一致し、読込みexit0。
Stageは両方schema0、DynamoDBはschema1。schema upgradeが必要な差は検出されなかった。
合成コピーの不正JSON、将来State形式version999、将来Stage schema999はすべてexit1で拒否された。

認証環境を継承せず、空のHOME、checkpoint無効、ローカルProvider配置だけで実行した。
init/plan/apply/refresh、remote backend読取り、AWS API、State原本変更は0。
Windowsのnetwork namespace隔離はしておらず、一般的なnetwork isolationの証明とはしない。
実Providerを使うPlan、import、refresh、将来版への移行・downgradeの検証ではない。

## 原因分類

| 分類 | 判定 |
| --- | --- |
| A 古いState | 現行と同じCLIでありschema読込み成功。今回の直接原因を支持しない |
| B Provider schema互換性 | 保存schemaは現行と一致し全State読込み成功。Plan002はinit前に停止 |
| C Apply途中失敗 | 元Workflow失敗とState/AWS差分から可能性はあるが直接原因はUNKNOWN |
| D Apply後drift | 可能性はあるがCと区別するwrite履歴・元Apply終了証拠が不足 |
| E CI承認・認証・実行器 | Plan001の搬送不備は再現。Plan002はpre-init live/readiness区間。Environment APIの現在の403は実測、当時の直接原因としてはPROBABLE |
| F その他 | 今回のローカル復号launcherのPowerShell module探索不備は別のCONFIRMED不具合 |

## 実行フェーズ

| 処理 | Plan001 | Plan002 |
| --- | --- | --- |
| Workflow/setup/locked dependencies | SUCCESS | SUCCESS |
| 事前検証・承認照合 | UNKNOWN（hash拒否を再現） | SUCCESS（approval/run-bound） |
| GitHub履歴照合 | UNKNOWN | SUCCESS（run-bound） |
| OIDC/STS/CallerIdentity | UNKNOWN | SUCCESS（STS response/CallerIdentity完了） |
| State snapshot読取り・承認照合 | UNKNOWN | SUCCESS（後続コード到達から確認） |
| 既存ArtifactのState内binding | UNKNOWN | SUCCESS。実S3/Lambda全体の再検証とは別 |
| CLI version subprocess | UNKNOWN | SUCCESS、exit0。1.14.9照合を通過 |
| Stage/AWS closure・GitHub readiness照合 | UNKNOWN | FAILURE区間、個別失敗条件UNKNOWN |
| Provider初期化 / Terraform init | UNKNOWN | NOT_REACHED |
| Terraform plan / 差分監査 | UNKNOWN | NOT_REACHED |
| saved Plan保存 | UNKNOWN | NOT_REACHED |
| journal暗号化保存 | FAILURE | SUCCESS |

## 最小実装修正

標準Plan経路にfinite diagnosticを追加した。公開するのはfailure_stage、failure_class、
reason_code、process_started、process_exit_observed、terraform_command_kindだけ。
schema_versionを併記し、未知値はunknown/ExternalOrScopeFailureとする。
承認前の拒否、subprocess launch失敗、exit観測、live各段階、readiness読戻しを区別する。
job tokenの特定Environment variables APIでの403は固定reasonへ分類する。
例外本文、URL、headers、token、AWS識別子、State、raw出力は公開しない。

既存workflow、IAM、認証方式、readiness条件、承認条件、retry回数、コマンド、版を変更していない。
この修正は診断欠落の修正であり、未確定のPlan002実根因の解消を意味しない。
Environments権限を持つ新資格の導入やreadiness照合の代替は運用境界に関わるため実装しない。

ローカル重点215件PASS、全Backend Ruff/format PASS。CIの最終結果はPRで確認する。
Windows全suiteの再実行はせず、Linuxの真正Actionsによる全Backend/Frontend/P4 offlineを用いる。
State異常系の実CLI検査3件、Operator helperの合成鍵・projection等8件もPASS。

## AWSを使用しないGitHub権限実測

[診断CI Run40490610980](https://github.com/yonegen0/ai_interview/actions/runs/40490610980)
（source a9bc7bbae7fc0fec35a1074807c55004a90705ba、2026-10-27 19:43 JST）で、
標準Planと同じcontents/actions/deployments readのjob tokenを用い、対象APIに各1 GETした。
dev-plan、dev-applyともHTTP403。応答本文は読取り・保存せず、tokenも出力していない。
OIDC権限、Environment指定、checkout、外部action、AWS資格情報は付与していない。
標準Planとの差であるid-token権限はOIDC発行用で、Environment APIへの権限を付与しない。
一時診断workflowは観測後に削除し、最終差分には残さない。既存運用workflowは変更していない。

これにより「現在の同じjob tokenでreadiness照合APIを成功させられる」という前提は否定された。
Stage照合が先に失敗する可能性は排除できず、Plan002の過去の最初の失敗条件はUNKNOWNを維持する。

## 復号helperの障害と修復

最初のlauncherはPowerShell5.1へPowerShell7由来のPSModulePathを継承し、path-0の組込み
cmdlet解決でCommandNotFoundExceptionになった。これは復号前の失敗であり、decrypt/projection
のexit codeはNOT_REACHED。鍵不整合・パスフレーズ誤り・projection不具合と推定しない。
既存helperに記載済みの鍵/cert固定パスのみを使用し、鍵探索・権限変更を行わなかった。

5.1組込みModulesへの固定と明示import後、実CMSの受取人/構造事前検査がPASS。
合成RSA鍵で正常復号exit0、認証tag改ざんexit4、projectionの秘密文字列除外を検証した。
その後の本人操作で実journal復号exit0、projection exit0、新規平文cleanup成功を確認。
秘密鍵・passphrase・復号原文は出力・送信しない。実journalの再復号は不要。

## 次工程・停止条件

実Runの具体的なStage応答・GitHub API HTTP拒否は既存journalにない。
追加のAWS診断、新Plan、旧Run再実行で証拠不足を埋めない。
既存元Applyの終了証拠が不足するため、元Apply正常終了UNKNOWN・公開NOT_READYを維持する。

次回Plan準備は未完了。新しい承認パッケージは最終化していない。
GitHub Environment読取り資格の承認済み設計・既存監査証拠での根因確認を先に行う必要がある。
新資格や既存運用workflow変更が必要な場合は、具体的な案を別途承認対象とする。
診断PRのmerge、新Plan、State/lock/readback、saved Plan専用Applyはそれぞれ既存の承認境界に従う。
AWS操作・Secret操作・readiness変更・dispatch・実AI・main mergeは本作業で0。

運用境界の修正案（未実装・未承認）は、対象repositoryに限定したGitHub Appの短命installation
tokenにEnvironments(read)を付与し、上記2つのvariables GETだけに別資格を渡す方式とする。
既存GH_TOKENを全体で置き換えず、PAT・別tokenへの自動fallbackも設けない。
取得前に有効期限・repository・権限・対象URLを固定し、AWS資格取得前にAPI capabilityを検査する。
readiness値の照合、片側だけtrue、既存承認・回数・AWS費用上限は維持する。
App credentialの保管と既存workflow変更は別の承認範囲であり、ここでは作成・読取り・設定しない。
採用前に専用fixtureで200/403/404/期限切れ/対象違い/redirect/欠落flagを検証し、
承認されたGitHub-only検証の後、新source SHAに対する1回限りのPlan承認を作る。
本PRの診断修正だけでは、この403を解消したことにも次回Plan準備完了にもならない。

## 公式根拠

- [gh2.102.0 Secret入力のCR/LF除去](https://github.com/cli/cli/blob/v2.102.0/pkg/cmd/secret/set/set.go#L383-L401)
- [Terraform1.14 State](https://developer.hashicorp.com/terraform/language/v1.14.x/state)
- [showとProvider schemaの条件](https://developer.hashicorp.com/terraform/cli/commands/show)
- [Provider6.65.0 Stage実装](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/stage.go)
- [GitHub Environment変数APIの権限](https://docs.github.com/en/rest/actions/variables#list-environment-variables)
- [GITHUB_TOKENで選択可能な権限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)
