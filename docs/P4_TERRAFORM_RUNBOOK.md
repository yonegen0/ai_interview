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

以下のPowerShellコマンドは、リポジトリの`backend`ディレクトリから実行する。
パスやhashは実行者が確認した値に置き換える。実行ごとに終了コード0と期待するstatusを確認する。

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
以後のinspect/migrate/verifyも、applyしたattempt番号を使用する。SHA・入力の変更を伴う修復は自動対応しない。

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
  "jpy_per_usd": "<承認済み換算値>",
  "budget_rate_date": "<YYYY-MM-DD>",
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
