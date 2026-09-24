# P4 継続実行計画

初版: 2026-09-13。最新状況追記: 2026-09-23。
正式な前工程表記は **P3実装完了・Python検証完了・実DB検証待ち**。
P4は実装継続中。以下は実施計画であり、AWS配備・試験成功の記録ではない。
実行結果は [P4_VERIFICATION.md](P4_VERIFICATION.md) に分離する。

## 決定事項

- Repository: 実remoteで確認した `yonegen0/ai_interview`。
- 専用dev Account、Region `ap-northeast-1`。実Accountはローカル `.env.local` の
  `AWS_DEV_ACCOUNT_ID`、CIではEnvironment `dev` のVariableから明示取得する。
- `.env.local`、`.p4-artifacts/` はGit管理外。Credentialを設定ファイルへコピーしない。
- GitHub Environmentはdevだけ。main branchだけを許可し、Required Reviewerは必須にしない。
- PR/featureはAWS非接続。実plan/apply/実DB試験はmainから手動起動＋OIDC。
- Fake Provider固定。FrontendはMSW維持。localhost:3000だけをCORS許可。
- 月3,000円相当をUSDに換算し、小数2桁切捨て。換算値と基準日は明示入力。
  50/80/100%通知。1試験100円相当は異常検知基準でありhard limitではない。
- 新しいRuntime/CLI/Python依存を先回り追加しない。既存lockを更新しない。
- P5、実Provider、Frontend実接続、実個人データ投入は対象外。

## 実装順と残作業

### 2026-09-23の残タスク判定

後続更新：下表の2つの技術的未達条件について、公開dev backendから旧bucket名を除き、
State由来の正しい実設定をprivate HCLへ分離したうえで、
`recovery_migration.py`によるhash固定handoff/既存migrationエンジンへの接続を追加した。
read-only inspectは成功。通常suite696件（新規42件）とTerraform mock24件/4 root validateも成功。
ただし新コードは未commitでCI未実行。移行承認、force-copy例外の判断、直前認証/排他/権限確認が
残るためNOT READY。詳細は[P4検証記録の後続更新](P4_VERIFICATION.md)を優先する。
下表は初回棚卸しの履歴であり、移行そのものやP4全体の完了を意味しない。

対象SHAは`ba28157aa34c536bc481a0d80e8714edd9132d5a`。
実測結果・run IDは[P4検証記録の最新節](P4_VERIFICATION.md)を参照。
根拠は本計画のDB/AS/AU/運用項目、`P4_IAM_AUDIT.md`、既存検証記録、
`.github/workflows/{backend,frontend,p4-static}.yml`、`backend/skills/p4/bootstrap_state.py`。
offline成功を実AWS試験完了へ読み替えない。以下は残作業の可視化であり、実行の承認ではない。

| 領域 | 判定 | 根拠・残タスク |
|---|---|---|
| bootstrap State復旧 | 完了 | 承認済みState-only更新、B/34/32維持、AWS前後一致、normal no-opを既存private記録で照合 |
| bootstrap完全読戻し/移行接続 | 実装残・別途レビュー待ち | 復旧readbackはあるが通常binding/journal形式ではない。標準読戻しの必須項目との対応、入力/構成/SHA/Stateの接続を設計・試験する。成功journalを偽装しない |
| State運用 | 別途承認待ち・未達条件あり | S3移行未実施。dev backend bucket不一致の意図確認、serial 34直前backup、VersionId付き一致確認、移行後no-opが必要 |
| CI/package | offline範囲は完了、実配備は未検証 | 3自動CIとterraform/package両job、Linux ZIP import成功。保存plan制御はoffline試験あり、実AWS保存/適用/中断再開の証拠は別 |
| 閉鎖dev配備 | 実装済み／実機未検証・別途承認待ち | 全機能停止で配備しmanifest v2の全設定を読戻す。配備workflowは今回起動しない |
| IAM/前提条件 | 実装済み／実機未検証が残る | auditとtrust/policy整合は許可/拒否smokeの代替でない。quota、SES送信可否、実OIDC→STS認証を確認 |
| DB | 実装残・実AWS証拠待ち | 既存57件は今回除外。DB-01〜20との不足対応・追加試験・実AWS実行結果を揃える |
| AS | 実装残・実AWS証拠待ち | run専用観測資源、試験ZIP、hard stop、配送/再配送/障害/限定redriveの不足を埋める |
| AU | 実装残・実AWS証拠待ち | OTP/JWT、全Route本人分離、他issuer/client、CORS、期限/失効/refresh/漏出検査を完成 |
| 運用 | 実装済み部分あり／実機未検証 | 検出→通知、負荷、費用、rollback、再構築、限定cleanupの実証 |
| 証拠管理 | 未確認部分あり | R01〜22/C01〜15それぞれにcommit・実行・成果物を紐付ける。通常654件/契約102件だけで網羅完了としない |

移行実行器の引継ぎ改造、実機試験、AWS変更を今回は追加しない。
次段階の停止条件・承認対象は[P4 runbook §5.1](P4_TERRAFORM_RUNBOOK.md#51-recoveryからのs3-state移行直前チェックリスト)にまとめる。

### 初版時点の実装順（履歴）

以下の表の「Linux実importのCI実行」など、後日完了した項目は上の最新判定を優先する。

| 段階 | 現在の実装 | 完了までに必要なこと |
|---|---|---|
| 410 設定/Guard | 非実行dotenv読取り、STS、Terraform入力競合拒否、run別manifest、bootstrap State移行実行口 | bootstrap実行と証拠確認、全経路の拒否試験 |
| 412 Runtime | 3起動口、claims、予算、alias、監視、ZIP生成 | 配布成功系試験の拡充、Linux実importのCI実行、読戻し全設定の照合 |
| 413 Terraform | 専用資源、SES bootstrap集約、4 CI Role、Budgets | IAMの実対応監査、bootstrap移行、Scheduler監視不足の照合、quota/SES検証 |
| 415 CI | AWS非接続CI、手動保存plan/apply、数値差分要約、実DBworkflow | GitHub実行、全CI制御の異常系試験、非数値差分の限定閲覧手順 |
| DB | 既存実DB57件、Account確認、作成/削除journal | DB-01〜20の不足分を追加し実行。既存57件を全仕様網羅とは扱わない |
| AS | Repository/adapterのローカル試験 | run専用観測Table/試験ZIP/hard stop/配送障害/限定redrive試験の実装 |
| AU | 対話OTP、6 API、別owner GET、ID Token、logout/期限 | 他issuer/client、全Route本人分離、CORS、停止/refresh、漏出検査を完成 |
| 運用 | Alarm定義と静的設定 | 検出→通知、負荷、rollback、再構築、費用推計、cleanupの実証 |

不具合修正は失敗再現→最小修正→関連試験→通常全体検証の順。
部分実装を「P4実装完了」と表記しない。

## Terraform実行手順

### 1. AWS非接続の確認

プロジェクトルートから、既に初期化されたローカル環境で実行する。

```powershell
terraform version
terraform fmt -check -recursive terraform
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/environments/dev validate
terraform -chdir=terraform/environments/test validate
terraform -chdir=terraform/modules/service test
```

未初期化環境では対象rootで `init -backend=false -input=false -lockfile=readonly` が必要。
Providerの新規取得が必要なら、その導入許可を先に確認する。`-upgrade`は使わない。
mock testはAWSや実Stateとのplan差分ではない。

### 2. 初回bootstrap（まだ実行しない）

実装/環境前提の確認後、利用可能な短期認証でAccount Guardを実行する。
Identity Centerを無条件に新設せず、長期Access Keyを新規発行しない。

bootstrapの入力は `account_id`, `region`, `oidc_subjects`, `ses_identity_type`,
`ses_from_email`, 必要時の`ses_domain`と`oidc_provider_arn`。
`oidc_subjects`はartifact/plan/deploy/testの4キー。実Claim確認前に値を推測しない。
既存OIDC Providerは明示ARN参照のみ。別プロジェクトの資源をimportしない。

bootstrapはlocal Stateで開始し、`backend/skills/p4/bootstrap_state.py`を専用実行口とする。
2026-09-14にinspect/replan、明示的な移行再開、読戻し、attempt別保存を追加した。
実行前提と具体的コマンドは [P4_TERRAFORM_RUNBOOK.md](P4_TERRAFORM_RUNBOOK.md) を正とする。
1台・1人で実行し、別hostから同時に操作しない。AWS上での成功はまだ未検証。
直接`terraform apply`せず、実行口だけを使う。入力JSONは`.p4-artifacts/`配下へ置き、
`oidc_provider_arn`, `oidc_subjects`（artifact/plan/deploy/test）, `ses_identity_type`,
`ses_from_email`, `ses_domain`の完全な5キーだけを含める。実値をログや文書へ転載しない。
cleanなmainと実remote、`P4_AWS_EXECUTION_READY=true`、
`P4_BOOTSTRAP_STATE_READY=true`をすべて要求する。

CLIは`bootstrap_state.py plan|apply|inspect|replan|migrate|verify --inputs <private-json> --directory <private-run> --attempt <番号>`。
applyには`--plan-hash <reviewed-sha256>`を追加する。同じrunを全段階で使用する。
planは新規runだけ、applyは未試行だけ、migrateはapply完了後だけを許可する。
attempt記録がある失敗操作を再実行せず、Stateと記録を監査する。記録を消して再試行しない。
verifyは同じS3版とreceiptの照合を繰返せる。`bootstrap-operation.lock`が残存した場合は
先行プロセスとStateを確認するまで解除しない。別hostからの操作はこのlockでは防げない。

実行口は新規のprivate runディレクトリへ設定だけを複製し、local backendでinit/plan/applyする。
各段階でSTS Account Guardを再実施し、2 Bucketのversioning/AES256/public block/TLS拒否、
OIDC Provider、4 Role、permissions boundary、SES IdentityをAWSから読み戻した後だけ移行する。
移行直前に`pre-migration.tfstate`を排他的に保存し、S3 backend宣言をrunディレクトリだけへ追加して
`-migrate-state -force-copy`を実行するのは移行先の不存在を確認できた場合だけである。
失敗時は原本backupを保全し、local Stateを無条件に復元しない。自動cleanupしない。
成功時は指定S3 VersionId/AES256とlineage/serial/resources/outputsを照合する。
State S3にはversioning、暗号化、TLS、public block、prevent_destroyを維持する。
移行先は `bootstrap/terraform.tfstate`、devは `dev/terraform.tfstate`、試験はrun別key。
State所有を重複させない。SES Identityはbootstrapだけで管理する。

### 3. GitHubの設定

mainにコードを反映する操作は、別途明示されたコミット/push許可の範囲で行う。
ローカルでworkflowを作っただけではGitHub上で実行できない。

Environment devに次を設定する。

| Variable | 内容 |
|---|---|
| AWS_DEV_ACCOUNT_ID | dev Account ID。Secret扱いは不要 |
| P4_OIDC_SUBJECT | 実Repositoryで発行確認した完全なsub |
| P4_DEPLOY_INPUTS | 以下の環境別JSON。実メールはコードに埋め込まない |
| P4_AWS_EXECUTION_READY | 初期は未設定。G0/G1、権限・費用・SES・quotaの前提を確認し、AWS実行が承認された後だけ文字列true |

`P4_DEPLOY_INPUTS`のキー:

```text
boundary_arn
ses_email
ses_identity_arn
alarm_email
jpy_per_usd
budget_rate_date
worker_enabled
streams_enabled
scheduler_enabled
api_enabled
```

初回は4つのenabledをJSON booleanのfalseにする。artifactのbucket/key/version/hashは
workflowが生成するので、この入力へ含めない。換算値は正の数値を表す文字列、基準日はYYYY-MM-DD。
入力やState/保存planにはメールが入るため、アクセスを制限し、チャットや公開ログへ転載しない。

Deployment Branch Ruleはcustom ruleのbranch `main`だけ。tagやwildcardは禁止。
実行ゲートが未確認ならjobをskipして成功扱いにせず、認証前に失敗させる。
artifact/plan/deploy/testは同じdev Subjectを信頼するため、Role分離だけでは
同じ信頼対象workflow間の認証分離にならない。workflow変更権限が重要な管理境界となる。
CIはRESTで設定を確認し、不明/アクセス不可なら認証前に停止する。
GitHub APIにtypeが返らない等、branch/tagを確認できない応答も成功扱いしない。
OIDC decoderは事前照合であり、署名の検証はSTSが行う。

### 4. 実plan（AWS実行許可とG0/G1完了後）

GitHub Actionsの **P4 manual dev plan or saved-plan apply** をmainから手動起動する。
operationは`plan`。AWS認証前に通常検証/ZIP検証を実行する。

- 現main SHA、Repository、Environment、Accountを照合。
- artifact Roleで同じZIPを一意S3 keyへ保存。VersionId必須、上書き禁止。
- plan RoleでState読取り/lock/実plan。
- artifact Roleで保存planとbindingを限定S3 prefixへ保存。
- run ID、attempt、plan SHA-256を安全な出力として記録。

通常plan出力には機微情報が混入し得るため、そのままCIログへ出さない。
hashだけでは差分レビューの代わりにならない。summaryにはresource type、action、許可した数値/真偽値差分だけを出す。
IAM policy、メール、任意before/after、resource addressは出さない。非数値差分はアクセス制限した
保存planと対象コードで別途レビューする。要約だけを完全な権限レビューと扱わない。

### 5. 保存planのapply

同workflowをmainから再度手動起動し、operation=`apply`、成功planのrun IDと確認したhashを指定。
plan後にmainが進んだ場合は再planする。State更新で古くなったplanも再生成する。

- 元workflowのsuccess、main SHA、operation、S3 Object VersionId、hashを照合。
- Terraform版1.14.9、lock hash、全入力hash、Account、Region、State keyを照合。
- STS確認後に同じ保存planだけをapply。`-auto-approve`や再planによるすり替えはしない。
- API/Table/Queue/Cognito/Lambdaの読み戻しを実施する。
- `applied_readback_verified`は読み戻し対象が一致した意味であり、P4実機試験全合格ではない。

### 6. 有効化と実機試験

G0通常検証→G1bootstrap/認証/Account→G2基盤読戻し→G3起動/IAM smoke→G4実DB→
Worker mapping→Streams mapping→Scheduler→API公開→OTP/E2E→障害/負荷/監視の順。
予約並列2が使えなければquota対応待ち。初回から全enabledをtrueにしない。

実DBworkflowは **P4 manual real DynamoDB tests**。runで作成確認したTableだけを削除し、
削除待機完了まで記録する。作成応答喪失はattemptedのまま残し、推定で削除しない。
CI artifactの`plans/db-<run>/<attempt>/tables.jsonl`は資源journalであり、テスト網羅の証明ではない。

## 試験・証拠の規則

- 通常pytestは `not dynamodb and not aws_e2e`。既存通常試験をAWS markerへ移さない。
- 実DBの収集だけではAWSクライアントを作らない。設定不足/接続失敗は失敗。
- GSIは1秒間隔/60秒上限、正常完了は2秒間隔/180秒上限。
- lease/deadline/DLQ/15分超障害には独立した上限を設ける。
- DB-01〜20: 強整合Getでrev/部分保存なし、独立process、実commit応答破棄、GSIを証明。
- AS-01〜18: hard stopはrun専用ZIPのみ。通常Provider例外と区別する。
- Provider進入はrun専用観測領域へrun ID/評価hash/execution ID/時刻だけを保存する。
  観測失敗は不合格。EMFから厳密回数を推測しない。
- AU-01〜15: 実OTP/実JWT、6 API、利用者分離、CORS、失効、IAM、ログ非漏出。
- 負荷は101×3 partition、1,000×3 partition、通常評価100件の順。並列2を維持。
- Alarmは障害注入→メトリクス→遷移→通知到達→復旧の時刻を記録する。

R01〜04/C04〜06→DB-01〜07/13、R05〜08/C07→AS-01〜06/12/16/17、
R09〜12/C08→AS-07〜11/DB-07、R13〜14/C09〜10→DB-09〜12/18/19、
R15/C13→DB-17/AU-13〜15、R16/22→DB-20/AS-18、R17→AU-02/08/DB-08、
R18/C11→DB-14〜17、R19→AS-13〜15、R20/C14→DB-08、R21/C03/12→結果保存境界、
C01/02→6 API/原文保持、C15→Guard/fixture/CI/cleanupを追跡する。

## 停止・復旧・完了

不一致、設定不足、Credential漏出、異常なInvocation/再配送/費用で停止する。
API閉鎖→Scheduler/Streams/SQS mapping停止→最大timeout待機→alias切戻し→
Worker/Streams/Scheduler再開→保存状態から回復→正常確認後API再開。
terminal/started/deadlineやStateを過去へ書き戻さない。

cleanupはrun Stateと作成確認journalが一致した資源のみ。dev Table、State S3、SES共通Identity、
biz-karteは対象外。cleanup失敗を残し、テスト本体成功だけでrunを成功にしない。
全必須証拠が揃うまでP4完了にしない。P5/本番配備へ自動移行しない。

公式参照: [S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)、
[GitHub OIDC](https://docs.github.com/en/actions/reference/security/oidc)、
[Environment branch policies](https://docs.github.com/en/rest/deployments/branch-policies)、
[Cognito email](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-email.html)。
