# P4 コスト・ログ最適化 Windows引き継ぎ（2026-10-09）

CloudでPhase 1/2と安全なPhase 3を実装した。AWS照会・変更、SSO、実State plan、Artifact upload、apply/destroy、Enablement/Closureは一切実施していない。Git pushの許可をAWS変更の承認に流用しない。既存cold-start性能GateのFAILは維持する。

## A. Gitと成果物

- repository: `https://github.com/yonegen0/ai_interview.git`
- branch / remote branch: `codex/p4-cost-log-optimization-20261009` / `origin/codex/p4-cost-log-optimization-20261009`
- 実装元HEAD: `b9ec1f7b02374639ff8eb7310e978b5950565757`。開始時`fetch origin main`・祖先確認でorigin/mainと一致、ahead/behind 0/0。Windowsにのみ存在するcommitの有無はCloudから確認できない。
- 実装commit / 最終remote一致 / PR / CI: この文書末尾「成果物確定記録」を参照。文書自身のcommit SHAは自己参照を避け、`git log -1 --format=%H -- docs/P4_COST_LOG_WINDOWS_HANDOFF_20261009.md`で取得する。
- 作業開始時からの`docs/INFRASTRUCTURE_OVERVIEW.md`変更は今回commitから除外し、元の変更を残した。今回成果物以外を一括stageしていない。
- 正式Artifactのimmutable sourceは新実装commitで固定する。文書だけの後続commitとArtifact source SHAを混同しない。

## B. 実装内容と修正ファイル

| 対象 | ファイル | 内容 |
|---|---|---|
| Terraform用途／retention | `terraform/environments/dev/{variables,main}.tf`, `settings.example.tfvars`, `terraform/environments/test/{variables,main}.tf`, `terraform/modules/service/{variables,runtime,auth}.tf` | `log_usage` developer=3日/customer=14日、dev必須、moduleの安全なdefault customer。API/Admin/Worker/Dispatcher/Gateway全5group、既存名前/address維持。GatewayアクセスにrequestTimeEpoch/responseLatency |
| 監視 | `terraform/modules/service/monitoring.tf` | developer dev17、customer dev21/22参照。既存17不変。customer追加PendingAge/QueuedAge>120秒、5xx>=1、EvaluationFailed（Worker+Dispatcher）>=1。60秒/1期間、missing notBreaching、既存SNS。Heartbeat missing breachingは不変 |
| test閉鎖 | test/service変数・monitoring | default39件42参照を維持。全4flags false、専用test run_id、`test_closure_confirmed=true`のときだけ`test_monitoring_enabled=false`可。再開時confirmation解除・monitor有効が必須 |
| 配備契約 | `terraform/modules/service/outputs.tf`, `backend/skills/p4/{cost_controls,manifest,manifest_checks,manifest_alarms,terraform_dev}.py` | manifest4、新用途入力をstrict承認bindingへ。schema2/3は旧保持日数／形式で検証し、旧証跡を書き換えない。新retention/Alarmの実機readbackに対応 |
| 相関／秘匿 | `backend/src/interview_backend/{operational_logs,observability,aws_runtime}.py`, `evaluation/events.py` | 評価ID、attempt ID、Lambda/Gateway request IDを受付→配送→claim→終端に連携。固定event/field allowlist、本文/JWT/token/email/例外文字列を出さない。warm context reset、logging失敗でも業務処理を再試行しない |
| 既存履歴再利用 | `backend/src/interview_backend/support_history.py`, `backend/skills/p4/support_history.py` | 既存exact-owner Evaluation snapshotをprivate summaryに変換。回答・採点本文を含めない。新item/table/write/TTLなし。過去provider不明はunknown |
| test drain補助 | `backend/skills/p4/test_monitoring_closure.py` | 読取り専用、全入口停止のmanifest/live照合、3queue（main+2DLQ）のvisible/inflight/delayedとWorkIndex全3partitionを2回60秒間隔で確認、manifest hash付きprivate観測記録 |
| 試験 | `backend/tests/unit/test_{operational_logs,p4_cost_controls}.py`, `test_p4_serverless.py`, `test_p4_{artifact_inputs,ci_readiness}.py`, `terraform/modules/service/tests/*.tftest.hcl` | 新39試験（ログ・監視34＋CI分岐5）、旧入力fixture更新、schema4/2/3・相関/秘匿/失敗/120日後/owner・Closure whitelist、保持/Alarm/gate mock |
| CI判定 | `backend/skills/p4/package_changes.py`, `backend/tests/unit/test_p4_serverless.py` | 新branch初回pushのbefore=0かつcreated/after/head整合時、比較元を推測せず必ずfull package検証。通常push/PR/manualの祖先検査を維持 |
| 文書 | 本書、`docs/P4_COST_LOG_OPTIMIZATION_PLAN_20261009.md`, `.csv`, `.json`, `docs/P4_TERRAFORM_RUNBOOK.md` | 実装状況、モデル費用、AWS未検証、既存runbookの新入力／manifest追記 |

Worker MaximumConcurrency=2、毎分Recovery、SQS retries/DLQ、DDB PAY_PER_REQUEST・冪等transaction・Streams、Cognito/JWT/owner、IAM/boundary/WIF、State方式を変更していない。SQS event形式は変えず既存evaluationIdを再利用する。IAM権限追加・新サービスは0。既存dev Closure実行器を変更していない。

90日以上の問い合わせは既存Evaluationが存続することが条件。120日後の読取り／owner分離をofflineで試験したが、AWS実保存、退会／管理者削除、バックアップ方針は未確認。TTLで回答・採点・処理recordを削除してはいけない。通常ログは14日で消え、requestIdはその期間の追跡情報で永続保存を新設していない。

Phase 3では正常GETの重複通常ログを抑制し、必要なEMFとGatewayアクセスログを維持した。既存EMFはProject/Environment/Componentの3低cardinality dimensionだけ。未実測のcustom3系列削除／EMFバッファ／新履歴基盤は実装していない。

## C. Cloud検証

| コマンド／検証 | 結果 |
|---|---|
| Backend `.venv/bin/pytest -q -m "not dynamodb and not aws_e2e"`（backend cwd） | **1200 passed、2 skipped、57 deselected、0 failed**。AWS/socket接続禁止fixtureを維持。skipは既存条件付き試験、deselectedはAWS依存 |
| `.venv/bin/ruff check .` / `ruff format --check src tests skills` / `interview-demo` | 成功 |
| Terraform1.14.9 `fmt -check -recursive terraform` | 成功 |
| `offline_terraform.py`方式：隔離コピーで4root `init -backend=false -input=false -lockfile=readonly` / `validate` | bootstrap/dev/test/serviceすべて成功。実StateもAWSも使わない。AWS Provider lock/signature維持 |
| 隔離service `terraform test` / bootstrap `terraform test` | **47+2=49 passed、0 failed**。developer/customer保持、customer21/22・test39/0・再開拒否条件を含む |
| Frontend Node22 `npm ci`, `npm run lint`, `npm run typecheck` | 成功、lintは既存生成cacheのwarning1（error0） |
| 正規`npm run test:unit` | **265 passed / 16 files** |
| Frontend全browser/E2E・各build | 下記成果物確定記録を参照 |
| locked production依存 export/install、Lambda ZIP build、展開offline import | 下記成果物確定記録を参照。正式AWS Artifact作成／uploadは未実施 |
| `git diff --check`、変更path・秘密情報・State混入監査、CSV/JSON整合 | 完了結果は成果物確定記録参照 |

Cloud環境: Python3.14.7、Terraform1.14.9、AWS Provider bootstrap6.64.0/dev-test-service6.65.0（既存lock）、Node22、uv0.12.19（CI固定0.11.8）、Next16.3.4。lockfile・CIのversionは変更していない。

一時領域のProvider重複で2回目のinitが容量不足になった。task専用コピーを削除し、同一hashのProviderをhardlinkで整理、初回init済み隔離コピーを現ソースに更新して4validate/49mockを再成功させた。元lock/stateは不変。frontend subprocessに必要な環境ネットワーク権限を付けて再実行した。テストを削除・閾値緩和して通していない。

Playwright公式Chromium153(v1243)の取得は配布domainのHTTP403で失敗。既存system Chromium151を、**一時configのexecutablePath**で指定する補助検証を行った。正式config・frontendソースは変更しない。一時config・build/browser成果物はcommitから除外し削除する。system版成功を正規Chromium版のCI成功と同一視しない。

未実施: AWS DynamoDB/E2E、OpenAI live、実State plan、IAM permissions-boundary実機、SNS inbox/OTP、負荷/cold-start性能Gate。既存Formal API p95<=2秒は**FAIL**（Scenario C 2003.466ms）を維持。新相関ログの実AWS性能影響は未測定、公開受入PASSではない。

## D. AWSで確認する項目

- Account/Region/SSO caller identityを最新のprivate承認入力と照合。Cloudには実値・現在のAWS状態がない。
- backend bucket/key/workspace、State lineage/serial/S3 VersionId/hash、lockなし、State外同prefix resourceを読戻し。文書の過去61baselineやserialを現在値として使わない。
- Git/main/source SHA、Provider lock、正式ZIP source/hash、S3 key/VersionId、Lambda CodeSha256/published version/aliasを照合。Python変更のため**新Artifactが必要**。既存Artifactを無断上書き／旧版へ巻戻さない。
- 新用途入力を全5group、Alarm、manifest4へ一致させる。旧schema2/3の実配備証跡はそのまま保持する。
- saved planの全resourceを監査。Log Groupはretention update、Gateway access format update、customer稼働なら追加4Alarmだけを期待。承認済み新Artifactに伴うLambda version/alias更新は別の明示範囲。DDB/SQS/Cognito/IAM/boundary/WIF/Streams/backend replace/destroy・説明不能な差分は禁止。
- **業務失敗Alarmの実機受入必須**：承認計画どおりFILL(wf,0)+FILL(df,0)、60秒/1期間を実装したが、[AWS公式metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)は遅配で最新期間が欠測の場合FILLがOK固定を起こし得ると説明する。offline試験はproducer/定義の検証で、CloudWatchの時刻評価を証明しない。Workerだけ／Dispatcherだけ／両方の単発失敗、正常無通信、60秒以上遅配した失敗を検証し、実際のALARM/SNS到達を確認する。検知しなければ公開受入を停止し、1-of-N等を別レビュー・saved planで修正する（4Alarm/5参照の料金は不変、計画の評価期間を無断変更しない）。
- SNS subscription Confirmed/通知到達、Missing Data/一時失敗/復旧、API5xx・EvaluationFailed・Pending/QueuedAge・Heartbeatを実機検証。故障注入は別承認の専用testを優先、顧客データを破壊しない。
- testは39Alarmを残して入口閉鎖・残務処理完了を確認。queue近似値／GSIはeventualなため、2回0だけで完全drainを保証しない。全writer停止、active Lambda、将来due work、DLQ原因・未解決障害、証跡の鮮度を確認する。
- 無料枠残量・AWS請求／Tokyo SKU、実取り込みbytes/custom metric hours/Alarm存在時間を取得してモデルを更新。新規credit型と常設枠を区別。OpenAI費用は別。
- 既存履歴の90日以上の存続と削除ポリシー、PITR/backup/RPO/RTOを公開前に確定。PITR追加はこのcommitに含まず別コスト・承認事項。

## E. Windowsでの作業順序

### 1. 取得と衝突確認（PowerShell、AWS不要）

既存Windowsrepoの未push commit・未commit変更を先に保存／確認する。`reset --hard`、clean、force pull、stash自動適用、既存branchへの強制checkoutはしない。

```powershell
Set-Location <既存ai_interview>
git status --short
git branch --show-current
git rev-parse HEAD
git log --oneline --decorate -12
git fetch origin
git log --oneline origin/main..HEAD
git log --oneline HEAD..origin/codex/p4-cost-log-optimization-20261009
git rev-list --left-right --count HEAD...origin/codex/p4-cost-log-optimization-20261009
# 衝突を避けるため別worktreeへ取り込む。新規directoryを使う。
git worktree add --detach ..\ai_interview-p4-review origin/codex/p4-cost-log-optimization-20261009
Set-Location ..\ai_interview-p4-review
git rev-parse HEAD
git status --short
```

末尾のremote確認SHAと比較する。Windows独自commitがある場合は差分をレビューし別branchで通常merge/cherry-pickを検討、欠落実装を上書きしない。新commitが入れば試験・Artifact SHA・planを再固定する。

### 2. Python/Terraform/WSLの確認（AWS不要）

```powershell
terraform version
uv --version
Set-Location backend
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check src tests skills
uv run --locked pytest -q -m "not dynamodb and not aws_e2e"
uv run --locked interview-demo
Set-Location ..
terraform fmt -check -recursive terraform
# 元Stateを避けるCI同等の隔離init/mock。元repoでinit -reconfigureしない。
python backend/skills/p4/offline_terraform.py --temp-parent <十分な空きのある一時directory>
```

既存WSLのLinux x86_64 CPython3.14環境を確認する。Windows native wheelをLambdaへ入れない。WSL上でrunbook §7／`p4-static.yml`の`uv export --locked --no-dev --no-emit-project`→`uv pip install --python-platform x86_64-manylinux_2_34 --only-binary=:all: --require-hashes`→`build_lambda.py`→socket禁止展開importの正式順序を利用する。`--code-sha`はGit raw blobsと一致するimmutable sourceを指定する。Cloudの暫定ZIPや古いupload承認JSONを正式配備へ流用しない。

### 3. AWS SSOとprivate入力（Windowsのみ、既存read権限）

```powershell
$P4Profile = '<既存承認済みSSO profile>'
aws sso login --profile $P4Profile
aws sts get-caller-identity --profile $P4Profile
aws configure get region --profile $P4Profile
```

Account/Regionはprivate承認値（Region ap-northeast-1）と一致させる。未知のAccountを推測で使わない。新権限/role/boundaryを足さない。sessionや.env/credentialsをGit/CIログへ出さない。SSO profileをCI WIFの代替にしない。

### 4. 正式planまで（AWS変更前に停止）

[P4 Terraform runbook](P4_TERRAFORM_RUNBOOK.md)を正本とする。`terraform_dev.py`/`p4-deploy.yml`は**最新origin/mainに一致するmain**を要求する。本branchの無断mergeやguard緩和は禁止。PRレビュー・merge承認が正式配備の前提となる。

1. branchのCI、Windows独自commit差分、private用途入力、Artifact計画をレビュー。mainへのmergeは担当者の別承認・実施。
2. 新mainのHEAD/remote一致と既存成功配備のprivate input/receipt/manifestを確認。新`log_usage`を明示し、他入力（Provider/WIF/Artifact条件/CORS/通知）を保全する。CI Environmentの`P4_DEPLOY_INPUTS`にも用途入力が必要で、この設定変更はCloud未実施。
3. backend/state/lockを既存runbook・`closure_aws.py`のread-only snapshot相当で確認。Stateをstdoutへ出さずprivate保存する。S3 head/getは固定VersionId、前後の同一性、lineage/serial/hash、active .tflock不在を確認。
4. 正式Artifactのbuild/upload承認・方式を確定。新Pythonで必要、`p4-deploy.yml`の通常planはbuild/uploadを伴うため、単に「read-only plan許可」でdispatchしない。正式uploadはAWS writeの別承認を得る。既存`upload-existing`経路の場合も旧承認を流用せず、新source/ZIP/provenanceを審査する。
5. runbook §8のmain/operation=planで正式saved planを作成する。既存ローカルCLI経路を使う場合も同じmain/明示credential/入力/bindingのguardを満たし、直接`terraform plan`を正式証跡の代用にしない。
6. private envelope、plan VersionId、binding/review/summary、State identity、ZIPのsource/hashを確認しsaved plan SHA256を固定。retention短縮前に必要なログ証跡をprivate保全する。
7. 全差分を監査し**apply承認待ちで停止**。想定外create/replace/destroy、古いState、lock、説明不能なIAM/version/alias変更で止める。

### 5. 別承認後のapply・実機検証・Closure

承認した同一saved plan/hashだけを既存runbookからapplyする。直前にState/main/Account/Region/Artifactを再照合する。エラー／partial failure時は無断再apply・新plan・手動修復をせずread-only診断して停止する。apply完了・readback失敗は既存verify手順に従い、applyを繰返さない。

成功後は全5retention、正確なAlarm数/属性/SNS到達、Lambda version/alias/Provider、owner/冪等性、相関ログ・秘匿を確認。実AI/30人/coldとwarmの正式Gate、429/5xx/timeout・backlog/DLQを確認し、過去cold FAILを証拠なしにPASSへ変更しない。

dev Enablementが必要な場合は既存承認テンプレートの条件付きClosureも同時承認する。Closureは全4閉鎖update＋今回承認した正確な17または21Alarm delete、それ以外baseline no-op、最新Artifact/version/alias保持。retention・基盤変更をClosureへ混ぜない。State外resource/lock/partial failureで停止。成功後API disabled、mapping Disabled、Scheduler DISABLED、Alarm0、State/Artifact/alias/lockを読戻す。

testの監視停止はdev Closure実行器とは別。test専用の入口停止saved planを承認し、**39Alarmを維持**して残務を解消した後にWindowsで次を使う（AWS read、環境guard必須）：

```powershell
Set-Location backend
# 全writer停止・既存read権限・Account/Region確認後、Windowsだけで明示する。
$env:AWS_PROFILE = $P4Profile
$env:P4_AWS_EXECUTION_READY = "true"
uv run --locked python skills/p4/test_monitoring_closure.py --manifest <private-test-deployment.json> --account <承認Account> --region ap-northeast-1 --output <backend/.p4-artifacts/新規drain-observation.json>
```

出力は削除承認ではない。manifest hash、観測時刻/run_id、全writer停止、queue近似値/GSI遅延、未解決障害なしを人が確認し、stale・不明・残務があればmonitorを保持する。その後だけ新test入力でclosure_confirmed=true/monitoring_enabled=false、全4falseを指定し、**Alarm39deleteだけ・他resource no-op**の新saved planを別承認する。apply後readback0、再開前confirmation=false/monitor=trueに戻し39を確認。Lambda/Scheduler掃除サービスを追加しない。

### 6. 14日を超える問い合わせ

利用者のJWTから得た正確なownerとevaluationIdを照合し、既存tableのexact GetItemを承認済みprivate端末へ保存する。scan・全user dump・新IAM権限は使わない。既存EvaluationキーはPK=`USER#<ownerSub>`、SK=`EVALUATION#<evaluationId>`。大文字小文字を変更せず、ConsistentRead=trueのexact GetItemを使う（`docs/p2/dynamodb-design.md`）。回答本文が含まれる原snapshotを共有/commitしない。

```powershell
Set-Location backend
uv run --locked python skills/p4/support_history.py --record <private-GetItem.json> --owner <問い合わせownerSub> --evaluation-id <UUID> --output <backend/.p4-artifacts/新規support-summary.json>
```

owner不一致・codec不明・古いrecordに必要情報が無ければ推測せず停止／unknownとする。private summaryにもuserIdが含まれるため最小担当者だけに共有し、既存ユーザー削除方針に従う。回答/採点/処理recordにTTLを設定しない。

## 費用

30人×20評価、720hモデル、USD、AWS実料金／残枠未取得。

| 条件 | 現行 | 顧客推奨 | 増分 |
|---|---:|---:|---:|
| 常設無料枠消費済み | $5.11/月 | $5.61/月 | 約+$0.50/月 |
| 常設無料枠に十分な余裕 | $1.12/月 | $1.62/月 | 約+$0.50/月 |

追加4Alarmは5metric参照×$0.10=$0.50/月。既存customを再利用、保守的4KB/評価のログ増・14日保存による微小増を含む推奨差は約$0.502665。test39Alarm/42参照の節約は`42×0.10×安全に削減した残存時間/月時間`、24hなら$0.14、実残存0なら0。無料10Alarm枠はAccount全体で共有する。料金公式頁はブラウザ経由で再確認したがTokyo全SKU・Account適用条件は未取得。通常Cloud shellの公式頁取得は403だった。新credit型無料プランは期間／残額の条件があり、無料運用保証に使わない。[CloudWatch](https://aws.amazon.com/cloudwatch/pricing/)、[AWS Free Tier](https://aws.amazon.com/free/)。OpenAIは別料金。実測削減額を捏造しない。

## 成果物確定記録

- 実装commit: `9d7f9846efcbb6bbafc6c869b1d2356a882f399d` (`feat: optimize P4 logging monitoring and cost controls`)。
- 通常`git push -u origin codex/p4-cost-log-optimization-20261009`成功。`git ls-remote`で実装commitの一致を確認。後続は検証記録／引き継ぎ文書のみのcommitを追加する。CI補修commitは`7e6cd45c3ccb2be24172a723cfb30f6a855887f1`（`fix: verify full Lambda package on initial branch pushes`）で通常push／remote一致確認済み。最新HEADは上記AのGitコマンドとPR headで確認する。
- [PR #1](https://github.com/yonegen0/ai_interview/pull/1)、draft、未merge。CIの実装元／補修commitの確認状態は下記。書面作成後の最新文書commitの結果はPR Checksでhead SHAごとに確認する。
- Cloud最終試験: Backend **1200 pass/0 fail/2 skip/57 deselect**、新39試験（ログ・監視34＋CI分岐5）を含む。Terraform **49 pass/0 fail**、全4root validate/fmt成功。Frontend全suiteはsystem Chromium補助で**654 pass/0 fail/61 files**、E2E **24 pass/0 fail**。正規unit265 pass、lint/typecheck、production/mock/Storybook build成功。
- 一時browser config削除済み、Frontend source/lock/workflow差分0。全変更38filesのみの初回commit、秘密key/State/Artifact混入なし、git diff --check成功。CSVは**48費用行＋16感度行**でJSON数値と一致。既存INFRASTRUCTURE_OVERVIEWの変更はhash不変で除外。
- Linux x86_64 CPython3.14 locked production ZIP: Git raw source blobs一致、2回のZIP byte一致、4handler/15questions/socket禁止展開import成功。ZIP sha256 `477af7dcef0e5c2a691bdfe87bbacf468555bb9696ad4d9c5c9cdff78b440c9b`、19,044,373bytes。Cloud検証用ZIPは`/tmp/p4-implementation/validated-1.zip`（session一時成果物、Git未格納／S3未upload）。Windowsで正式経路に従い再構築／source・依存・hashを再照合し、新承認を取る。Cloud検証hashをAWS Artifact承認の代用にしない。
- 通常git接続/pushは成功した。Cloudの`gh auth status`はGH_TOKEN invalidで失敗したため、PR/Actions readは接続済みGitHub connectorで行った。credentialの出力/設定変更をしていない。
- AWS変更の承認は未取得。正式deployment／90日実保存／SNS／性能の未検証項目はD/Eのまま。


### CI確認記録と継続確認

- 実装commit `9d7f984` のPR [Backend](https://github.com/yonegen0/ai_interview/actions/runs/37878810277)／[P4 Terraform・Package](https://github.com/yonegen0/ai_interview/actions/runs/37878810081)はSUCCESS。初回pushの[Package判定失敗](https://github.com/yonegen0/ai_interview/actions/runs/37878760581)はbefore=0の新branchイベントが原因、ログ確認・新5試験・full package分岐の補修済み。失敗runを削除／成功へ偽装しない。
- 補修commit `7e6cd45` の[Backend](https://github.com/yonegen0/ai_interview/actions/runs/37879087994)／[P4](https://github.com/yonegen0/ai_interview/actions/runs/37879088099)／[Frontend](https://github.com/yonegen0/ai_interview/actions/runs/37879088081)はこの書面更新時に実行中。正式Chromium版、test/build/E2Eの全step完了までCloud側で監視する。最終応答は最新headの実際の結果を報告する。
- Windowsは[PR Checks](https://github.com/yonegen0/ai_interview/pull/1/checks)で最新head SHAと全job successを再確認する。過去SHAのsuccessだけで新変更を配備しない。

### 最終文書commit直前の読戻し

- Cloud HEAD/remote一致確認済み: **`82ae05922c79d0d1f40a046e9bc636664477a76c`**（文書記録commit）。本追記は文書だけの後続commitに格納するため、自身のSHAはAのGitコマンドで解決する。実装source=9d7f984、CI補修=7e6cd45、文書=82ae059＋本追記という順序で、通常pushのみ、mainは未merge。
- このHEADの[Backend PR](https://github.com/yonegen0/ai_interview/actions/runs/37879234553)／[P4 PR](https://github.com/yonegen0/ai_interview/actions/runs/37879234663)、pushのBackend/P4は**SUCCESS**。Frontendの正式Chromium取得・lint/typecheck・全test・production/Storybook/mock buildは成功、[E2E](https://github.com/yonegen0/ai_interview/actions/runs/37879234688)は書面更新時進行中。実装元9d7f984の正式[Frontend全CI](https://github.com/yonegen0/ai_interview/actions/runs/37878810097)は**SUCCESS**。
- 本追記以降のruntime/Terraform/frontendの差分は0。Cloudは最終pushのCIも完了まで監視し、終了時の最新結果を最終応答へ記載する。Windowsは必ずPR Checksから最新SHAを再照合する。
