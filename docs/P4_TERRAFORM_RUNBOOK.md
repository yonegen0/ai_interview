# P4：閉鎖状態のdev初回配備手順

対象はbootstrap → S3 State移行 → CI保存plan → 閉鎖状態のdev apply。
AWS操作・GitHub設定変更・commit/pushは、この文書の存在だけでは承認されない。
最新の実装・検証状態は [P4_VERIFICATION.md](P4_VERIFICATION.md) を先に確認する。
Linux ZIP importとAWS上のIAM許可・拒否、通知到達、OTPはローカル成功から推定しない。

## 0. 実行前提

- 実行者は1人、bootstrap端末は1台。他端末・別cloneから同時実行しない。
- Terraform 1.14.9、Python 3.14、既存lockfileに対応した依存があること。
- 変更レビュー後、明示承認を得てmainへ反映し、cleanなmainを使用する。実行中はSHA・入力を変更しない。
- 東京の対象Accountを確認する。`.env.local`のAccountとRegion、必要ならAWS_PROFILEを設定する。
- AWS認証は既存の短期認証を使う。新規長期Access KeyやIdentity Centerを自動作成しない。
- `.p4-artifacts`はGit管理外・本人限定のprivate保管場所とする。共有フォルダ、junction、symlinkを使わない。
- `TF_LOG`、`TF_LOG_PATH`、`TF_CLI_ARGS*`、外部`TF_DATA_DIR`、非default workspace、endpoint上書きを設定しない。
- 保存plan、private review、Stateにはメールや資源識別情報がある。チャット・CIログ・公開artifactへ貼らない。

次の「Terraform CLIでの設定ファイル指定」節を除き、PowerShellコマンドはリポジトリの`backend`ディレクトリから実行する。
パスやhashは実行者が確認した値に置き換える。実行ごとに終了コード0と期待するstatusを確認する。

## Terraform CLIでの設定ファイル指定

この節は**リポジトリルート**から実行する。bootstrapとdevにはコメント付きの
`settings.example.tfvars`を用意している。実値はGit管理外の`settings.tfvars`へ記入する。
別端末や新しいcloneでは次のようにコピーする。既存のローカル設定は上書きしない。

```powershell
foreach ($tfRoot in @('terraform/bootstrap', 'terraform/environments/dev')) {
    $localSettings = Join-Path $tfRoot 'settings.tfvars'
    if (-not (Test-Path -LiteralPath $localSettings)) {
        Copy-Item -LiteralPath (Join-Path $tfRoot 'settings.example.tfvars') -Destination $localSettings
    }
}
```

1. 各`settings.tfvars`をエディタで開き、`REPLACE_ME`を実値へ置換する。
   bootstrapは確認済みAccount・実OIDC Subject・承認済みSES方式と送信元を記入する。
   devはbootstrapの確認済み出力、同一ZIPのS3 key・VersionId・Base64 SHA-256、送信元・通知先を記入する。
2. devの`cors_origins`に実Frontend originを、`monthly_budget_usd`に承認済みの正のUSD額を記入する。
   空のCORSはvalidationで拒否される。予算は3,000円÷160円/USD=18.75 USD（基準日2026-09-17）。Regionは東京、4つの有効化フラグはfalseを維持する。
3. 既存手順に従って短期認証とTerraform初期化を準備し、対象AccountとStateを確認する。
   devのS3 backend設定は`terraform -chdir=terraform/environments/dev init -input=false '-backend-config=<確認済みbackend設定ファイル>'`で別途指定する。
   backend設定ファイルの相対パスはdevディレクトリ基準。既存Stateの移行にこのinit例を流用せず、後述の移行手順に従う。
4. AWS操作の明示承認後、対象に応じて次のplanコマンドを実行する。

```powershell
terraform -chdir=terraform/bootstrap plan -input=false '-var-file=settings.tfvars'
terraform -chdir=terraform/environments/dev plan -input=false '-var-file=settings.tfvars'
```

各対象ディレクトリへ移動済みなら、共通して次を使う。

```powershell
terraform plan -input=false '-var-file=settings.tfvars'
```

`-input=false`により必須変数が不足しても入力待ちにならずエラーで終了する。
設定値の正しさやAWS接続成功を保証する指定ではない。追加の`-var`や複数の`-var-file`は使わず、
このファイルで値を管理する。`terraform plan`だけではこのファイルは読み込まれない。
tfvarsは資源変数用であり、S3 backend設定やAWS認証情報のファイルではない。
Credential・Tokenを記入しない。Terraform CLIは`.env.local`を直接読み込まない。

直接planはP4実行器の承認hash・journal・読戻しを生成しない。
正式な配備・State移行は以下のP4手順を継続する。bootstrapの直接planは実行ディレクトリのStateを使用するため、
P4作業ディレクトリのStateや移行済みS3 Stateと混同し、空のStateからの新規作成計画を適用しない。
既存P4実行器・CIは従来のJSON入力と環境変数を使用し、`settings.tfvars`を取り込まない。
自動読込される`terraform.tfvars`や`*.auto.tfvars`は既存Guardが拒否するため作成しない。

### ZIPの確定と構成検証

ZIPのkey・VersionId・Base64 SHA-256は、既存CIで固定ソース・依存からLinux ZIPを作成し、
展開・import検証後、versioning付きBucketへuploadした同一成果物から取得する。
ローカルで直接planするときだけ3値を同時に転記する。CI自体はこれらを自動生成するため手動設定は不要。
プレースホルダーのままならplanのvalidationで停止するのが期待動作。
形式検証はS3実在性・ZIPとのhash一致を保証しない。
`terraform validate`は構成の検証であり、`settings.tfvars`の実値検証ではない。

### 確認用planとprivate保存plan

`-out`なしのNoteはエラーではない。後の通常applyでは再計画され、表示内容と異なる可能性がある。
以下はリポジトリルートからの直接CLI用保存例。AWS操作の承認とZIP実値の確定後だけ実行する。
保存ディレクトリは本人限定とし、共有フォルダ・junction・symlinkを使わない。

```powershell
$privateRoot = Join-Path (Get-Location).Path '.p4-artifacts'
$planDirectory = Join-Path $privateRoot ('dev-plan-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $planDirectory) { throw 'Plan directory already exists' }
New-Item -ItemType Directory -Path $planDirectory -ErrorAction Stop | Out-Null
$planPath = Join-Path (Resolve-Path -LiteralPath $planDirectory).Path 'dev.tfplan'
if (Test-Path -LiteralPath $planPath) { throw 'Plan file already exists' }
terraform -chdir=terraform/environments/dev plan -input=false '-var-file=settings.tfvars' "-out=$planPath"
if ($LASTEXITCODE -ne 0) { throw 'Plan failed; do not review or apply its output file' }
```

保存planには入力値等が含まれる。Git・公開artifact・チャットへ掲載しない。
このファイルはP4実行器のbinding・承認hash・journal付き成果物として流用しない。
正式な配備は以下の既存手順で保存planをレビューして行う。
WorkIndexの記法変更後の実planでテーブル置換やGSI再作成が出た場合はapplyせず調査する。
offline mock成功は実Stateに対する無変更の証明ではない。

## 1. GitHub dev EnvironmentとOIDC Claim

明示承認後、RepositoryのEnvironment `dev`をmain限定で作成・確認する。
required reviewerは設定しない。workflowコードの変更権限を持つ人が配備Roleを利用できる境界である。
4 Roleの分離は権限セットの分離であり、同じdev Subjectを信頼する場合の人の分離ではない。

Actionsの **P4 OIDC claim discovery (no AWS)** をmainから手動実行する。
このworkflowはAWS認証を行わず、issuer/aud/sub/Repository識別情報だけを表示する。
Token本文を保存しない。表示されたsubを4 Roleの入力へ使用し、推測値を使わない。
Claim確認はJWT署名検証の代替ではない。実際の署名検証は後のSTSが行う。

## 2. private入力ファイル

`.p4-artifacts/bootstrap-inputs.json`に以下の5キーだけを保存する。
AccountとRegionはこのJSONに追加せず、Guardが`.env.local`から取得する。

```json
{
  "oidc_provider_arn": "",
  "oidc_subjects": {
    "artifact": "<実際に確認したdev sub>",
    "plan": "<実際に確認したdev sub>",
    "deploy": "<実際に確認したdev sub>",
    "test": "<実際に確認したdev sub>"
  },
  "ses_identity_type": "domain",
  "ses_from_email": "<承認済み送信元メール>",
  "ses_domain": "<承認済みドメイン>"
}
```

既存のGitHub OIDC Providerを使用するときだけ明示ARNを指定する。空文字は新規作成であり、
既存Providerを自動検出・importしない。email Identityの場合はtypeを`email`にし、domainキーは空文字にする。
SESの存在・検証済み・送信可能性は別判定。閉鎖配備は実OTP成功の証拠にはならない。

## 3. bootstrap planとレビュー

短期認証を準備した端末で、AWS操作の明示承認後にだけゲートを設定する。
profileと環境変数Credentialを混在させない。SDKで解決した短期CredentialをTerraformにも渡す。

```powershell
$env:P4_AWS_EXECUTION_READY = 'true'
$env:P4_BOOTSTRAP_STATE_READY = 'true'
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py plan --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
```

成功statusは`bootstrap_planned`。`bootstrap-initial`は新規ディレクトリでなければならない。
生成物は`bootstrap.tfplan`、`binding.json`、`summary.json`、`review.private.json`。
summaryは数値等の限定表示であり、信頼policy・メール・Bucket設定のレビューを代替しない。
private reviewとbindingをローカルエディタで確認し、表示されたplan SHA-256を承認する。
レビュー後にファイル、ソース、lock、入力を変更した場合はそのplanを使用しない。

## 4. bootstrap applyと読戻し

private review後、同じhashを指定してapply前の検査を行える。

```powershell
$reviewedHash = Read-Host 'レビュー済みbootstrap plan SHA-256'
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py preflight --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1 --plan-hash $reviewedHash
```

成功statusは`bootstrap_preflight_passed`。preflightは操作lockと診断記録だけを作成し、
Terraform init/plan/apply、State更新、apply journal作成は行わない。
Git・構成・binding・承認hash・認証元・SDKのSTS Account・短期Credentialをapplyと同じ処理で確認する。
資源作成権限・quota・資源重複は保証しない。applyはpreflight結果を使い回さず再検査する。
apply開始済みや後続attemptが存在するplanはpreflightでも拒否する。

```powershell
$reviewedHash = Read-Host 'レビュー済みbootstrap plan SHA-256'
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py apply --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1 --plan-hash $reviewedHash
```

成功statusは`bootstrap_resources_verified`。apply開始・完了・読戻し完了を別ファイルに保存する。
読戻し失敗時に同じplanを再applyしない。apply完了記録がある場合は次だけを再実行する。

```powershell
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py verify --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
```

## 5. S3 State移行

```powershell
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py migrate --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py verify --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
```

最終statusは`bootstrap_state_migrated`。`migration-receipt.json`にVersionIdとlocal/remote hashが残る。
`pre-migration.tfstate`は原本backupとして残す。移行後のlocal Stateは運用に使用しない。
S3 Stateが存在する場合の通常移行は禁止。403を不存在と扱わない。

## 6. 中断・失敗からの再開

```powershell
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py inspect --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
```

| 観測 | 許可する次操作 | 禁止する操作 |
|---|---|---|
| apply結果不明・Stateなし | 停止して個別調査 | 自動再作成、推測import、同じplan再apply |
| 部分apply・有効なStateあり | 次attemptのreplan、再レビュー | 旧attemptの記録削除 |
| apply完了・読戻し失敗 | verify | 再apply |
| remoteがbackupと一致 | verify | 再コピー、local運用 |
| remote不存在・localとbackup一致 | migrate --resume | 通常migrateの強制再実行 |
| remote不一致・読取り不能・State破損 | 停止して保全 | 上書き、cleanup |

部分applyの例：

```powershell
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py replan --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 2
```

新成果物は`attempts/0002`に保存される。新hashをレビュー後、同じrootと`--attempt 2`でapplyする。
以後のinspect/migrate/verifyも、applyしたattempt番号を使用する。入力・Terraform構成の変更を伴う修復は自動対応しない。

### 診断記録と認証失敗

実行器はTerraform stdout/stderrを`<run>/diagnostics/<UUID>/`へ直接保存する。
ファイルは新規作成限定で、`context.json`、連番の`*.stdout.private`・`*.stderr.private`・
`*-result.json`、最後の`outcome.json`を作る。outcome欠落は処理未完了であり成功を意味しない。
初期Guardが診断先作成前に停止した場合はdiagnostic_idがnullとなり、記録は作成されない。

Windowsでは新規UUIDディレクトリの継承を無効化し、実行ユーザー・SYSTEM・AdministratorsのSIDに
限定して設定・読戻し検査する。POSIXではディレクトリ0700、ファイル0600を使用する。
既存runのACLは変更しない。本人限定アクセスの確保に失敗したらTerraformを起動しない。
診断先のsymlink/junction、既存ファイル上書きを拒否する。記録失敗時もjournal・診断先を削除しない。

公開JSONは従来のstatus/failure/next_operationにstage/reason_code/diagnostic_idを追加する。
Terraformの非ゼロ終了時はreturn_codeも返す。原因の本文はprivateエディタで確認する。
診断にはメール、資源識別子、Stateなどが含まれ得る。チャット、CIログ、公開artifactへ貼らない。
環境変数・Credential・SSO cacheは診断metadataに転記しない。生のTerraform出力が秘密情報を
含まないことは保証しないため、TF_LOG等の既存禁止は維持する。

| reason_code | 対応 |
|---|---|
| MixedCredentialSources / PartialCredentials / CredentialProfileConflict | Profileと環境変数Credentialの競合・不足を解消する。値を表示しない |
| SsoTokenUnavailable | 実際にSSO方式のProfileの場合、実行者が既存SSOへ再ログインする |
| AwsAuthenticationRejected / AwsConnectionFailed / AwsIdentityUnavailable | Credential有効性・接続・SDK側の認証を確認する。CLIのSTS成功だけで代用しない |
| AwsAccountMismatch / ShortTermCredentialsRequired | 対象Account・短期Credentialの前提を修正する |
| TerraformNonZeroExit / TerraformStartFailed | stageとprivate stderrを確認する。apply開始済みなら再apply禁止、inspectへ |
| DiagnosticPermissionsFailed / DiagnosticStorageFailed | 診断保存先を調査する。apply開始済みなら結果不明としてjournalを保持する |
| BootstrapAttemptIncomplete / NewBootstrapAttemptRequired | 不完全または既存attemptを個別調査する。削除・上書き・飛び番での自動再開は禁止 |

`apply-attempt.json`が存在しなければ開始前の停止。ただし認証・binding等の問題を解消し、
再検査するまでapplyを繰り返さない。存在すれば完了記録の有無に従ってinspect/verifyへ分岐する。
過去の実行器が破棄したエラー本文は、この変更では復元できない。

### 診断コード変更後の明示的SHA引継ぎ

診断修正をレビューし、別途承認されたcommit/pushでcleanなmainへ反映した後に限る。
旧attemptのbinding/plan/journalを新SHAへ書き換えない。
`--previous-source-sha`はreplan専用であり、旧bindingの完全なSHAを指定する。

```powershell
$previousSha = Read-Host '直前attemptのbindingで確認した旧source SHA'
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py replan --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial-20260918-01 --attempt 5 --previous-source-sha $previousSha
```

上のattempt 5は、attempt 4が部分applyで、5がまだ存在しない場合だけの例。
旧SHAが現HEADの祖先であること、旧commit/現commitのTerraform構成・lockfile一致、
作業ファイル/run/bindingのhash一致、入力・Account・Region・Terraform版・backend・State key一致を要求する。
Git blob同士を比較してWindows改行変換を考慮するが、作業ファイルとbindingのhash一致条件は緩めない。
apply開始journalと旧plan hashの一致、完了記録なし、有効なlocal State、移行未開始、remote State不在を確認する。
403などは不在扱いしない。祖先関係はコードレビューの代替ではない。

新bindingはv2で、直前attempt・旧SHA・旧bindingファイルのhashをpredecessorへ記録する。
v1も読取り可能で旧ファイルを変換しない。apply/preflightでもpredecessorを照合する。
旧planの承認は引き継がず、新planのprivate review → preflight → hash承認付きapplyを行う。
構成や入力変更が必要ならこの引継ぎは拒否され、別の復旧計画が必要となる。

replan途中失敗で次attemptが残った場合は不完全なまま保全する。自動削除・再plan上書き・
飛び番再開は提供しない。診断記録を確認して個別に復旧を計画する。

移行再開の例：

```powershell
.\.venv\Scripts\python.exe skills/p4/bootstrap_state.py migrate --resume --inputs ../.p4-artifacts/bootstrap-inputs.json --directory ../.p4-artifacts/bootstrap-initial --attempt 1
```

remote不存在とbackup一致を再確認した場合だけ、途中で変化したbackend metadataをlocalへ再初期化して移行を再開する。
移行済みなら再コピーせずverifyへ進む。Stateの消失・相違は自動修復しない。

`bootstrap-operation.lock`残存時は自動解除しない。実行中のPython/Terraformプロセスがないこと、
他端末操作がないこと、journalとlocal/backupをprivate領域で確認する。確認記録を別名で保全してから
当該lockだけを退避し、inspectを実行する。Stateやrunディレクトリを一括削除しない。

## 7. CI設定

明示承認後、dev Environmentに`AWS_DEV_ACCOUNT_ID`、`P4_OIDC_SUBJECT`、
`P4_AWS_EXECUTION_READY=true`、`P4_DEPLOY_INPUTS`を設定する。Regionは東京に固定。
`P4_DEPLOY_INPUTS`は以下のキーだけとし、artifact情報はCIが生成するため追加しない。

```json
{
  "boundary_arn": "arn:aws:iam::<Account>:policy/ai-interview-runtime-boundary",
  "ses_email": "<承認済み送信元>",
  "ses_identity_arn": "arn:aws:ses:ap-northeast-1:<Account>:identity/<承認済みIdentity>",
  "alarm_email": "<承認済み通知先>",
  "jpy_per_usd": "160",
  "budget_rate_date": "2026-09-17",
  "worker_enabled": false,
  "streams_enabled": false,
  "scheduler_enabled": false,
  "api_enabled": false
}
```

初回実行器は全フラグfalseを要求する。有効化は今回の手順に含まれない。

## 8. CI plan → privateレビュー → apply

1. Actionsの **P4 manual dev plan or saved-plan apply** をmain、operation=`plan`で実行する。
2. Backend/static/package jobの成功を確認する。Linux ZIP importがAWS認証前に成功していること。
3. run ID、attempt、main SHA、plan hashを記録する。
4. 承認済みの読取り権限でartifact Bucketの`plans/<run>/<attempt>/envelope.json`を確認する。
5. envelopeが指定するVersionIdのplan・binding・private reviewをprivate端末へ取得する。
   ファイル内容をCIログへ出さず、非数値差分もレビューし、plan hashを承認する。
6. 同じworkflowをoperation=`apply`、`plan_run_id=<元run>`、`plan_hash=<承認hash>`で実行する。
7. `applied_readback_verified`とprivateの`deployment.json`を確認する。

apply内で再planしない。Stateが古ければ失敗し、新planとレビューが必要。
元planの`apply-started.json`だけがある場合は結果不明として再applyを拒否する。
`apply-completed.json`がある場合、同じ入力で再実行しても読戻しだけを行う。
mainのSHAが変わった場合は旧runを自動流用しない。

配備manifestはv2で、API閉鎖・全mapping停止・Scheduler停止を承認入力と照合する。
読戻しは2秒間隔・60秒期限。期限超過は失敗であり、applyを繰り返す理由にしない。

## 9. 終了後

private成果物を保持し、実行ゲートを無効へ戻す。破壊的cleanupは行わない。
結果は「閉鎖状態dev配備」として記録し、P4完了・公開可能・OTP/通知到達成功と記載しない。
実DB、IAM smoke、段階的有効化、AU/AS、運用試験は別の明示承認と実機証拠を必要とする。
