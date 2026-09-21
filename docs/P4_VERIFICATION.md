# P4 検証記録

## 2026-09-21：bootstrap診断・preflight・明示的SHA引継ぎ

今回の対象は実装とoffline検証。AWS操作・State移行・IAM/GitHub変更・commit/push・依存更新は行っていない。
以下の実run状態は既存ファイルの安全なメタ情報を確認した記録であり、今回のapply結果ではない。

- 既存runのattempt 4はapply-attemptあり、apply-completed/readback-completedなし。
  local State serialは21、SES email identityが1 instance。操作lock・移行記録なし。
  過去のinspectはpartial_apply/replan。attempt 1〜4の再applyは禁止のまま。
- 過去のTerraform失敗本文は保存されておらず、原因は未確定。State上の未記録はAWS上の不存在の証明ではない。
- Terraformの各段階を分類し、stdout/stderrを新規のprivate診断ファイルへ直接保存する実装を追加。
  公開JSONは固定reason_code/stageとdiagnostic_idだけを追加し、例外本文を出さない。
- 診断UUIDディレクトリはWindows SID指定の保護DACLを設定・読戻し検査する。
  合成一時領域で実ACLとローカルsubprocess出力保存を検証。既存run全体のACLは変更しない。
- preflightを追加。applyと共通の検査・短期認証照合を実施し、State・plan・apply journalは変更しない。
- replan専用previous-source-shaを追加。祖先関係、旧/新Git blob、run構成、入力、旧plan/review、
  apply journalを照合し、部分apply・移行未開始・remote不在の場合だけ次attemptへ進む。
  v2 bindingにpredecessorを記録し、v1は変換せず読取り互換を維持する。
- 不完全attemptの再利用・飛び番再開、診断保存失敗後の再apply、旧成果物の上書きを拒否する試験を追加。
- 最初のsandbox試験は新規pytest tempへのアクセス拒否で失敗したため、新しい合成tempで権限付き実行した。
  Windows Set-Aclが不要な監査権限を要求する問題を検出し、DirectoryInfo.SetAccessControlで必要なDACL/ownerだけを設定するよう修正。
  既存のアクセス不能pytestディレクトリや失敗試験の成果物は削除していない。

最終通常suiteは620成功・実AWS対象57除外（`.p4-artifacts/tmp-bootstrap-diag-full-02`）。
その後、未知例外も固定JSONを返す最終CLI境界の追加2試験が成功（既存suiteの再集計ではない）。
Ruff check成功、format check67ファイル適合、CLI helpとgit diff --check成功。
実AWSでの新診断採取・SHA引継ぎ・apply成功は未確認。
レビュー後のmain反映と新planのprivate review/hash承認を経て、別段階で実行する。
手順は [P4_TERRAFORM_RUNBOOK.md](P4_TERRAFORM_RUNBOOK.md) を参照する。

## 2026-09-18：dev設定・ZIP validation・WorkIndex記法の修正

ローカル修正・offline検証完了。AWS配備・P4全体の完了を意味しない。
以下は今回の追加検証であり、後続の539件等は過去の実行記録として保持する。

- WorkIndexだけをkey_schemaへ変更。Provider 6.64.0/6.65.0ともテーブル本体には
  key_schemaがなく、PK/SKのhash_key/range_keyを維持。非推奨警告はGSIの旧記法によるものだった。
- ZIP key/VersionId/hashの未記入・不正形式をTerraform/Pythonで拒否。
  検査は形式だけで、S3実在性やZIPとの一致を保証しない。
- ローカルAccount IDを引用符付きに変更。dev予算は18.75 USD
  （3,000円÷160円/USD、基準日2026-09-17）。その他の既存実値と閉鎖フラグを維持。
- PowerShell引数の引用符、private保存plan、既存CIからのZIP情報確定手順をrunbookへ追記。
- Python関連試験158成功（artifact inputs/tools/CI readiness/guard/bootstrap stages）。
  最初のRuff検査で追加テストの行長を検出し、整形後にcheck成功。
- Terraform service mockは6.64.0で23成功、6.65.0でも23成功。
  6.65.0は既存Providerをplugin-dirから使うbackendなし隔離領域で検証し、依存取得・更新なし。
  bootstrap mockは1成功。bootstrap/dev/test/service validate成功、対象非推奨警告なし。
- PowerShellの引用符付き引数をPython argvで非通信確認。fmt check、Git除外、diff checkを確認。
- devの最初のproviders schema取得は既存S3 backendがSTS接続を試み、sandboxのproxyで失敗。
  再試行でAWS接続を許可せず、backendなし隔離領域へ切り替えてスキーマを確認した。
  AWS上のplan/apply・GitHub操作は実行していない。dev既存lockfile変更6.65.0は保持。

残作業：ZIP実値の確定、AWS資源照合、実Stateに対するplanとprivate review。
テーブル置換・GSI再作成がないことはoffline mockでは証明していない。
実planで該当差分が出た場合はapplyせず調査する。

更新日: 2026-09-14。**閉鎖状態dev初回配備の実装・offline検証を追加。P4全体は未完了・AWS未実行**。
前工程は **P3実装完了・Python検証完了・実DB検証待ち**。
計画は [BACKEND_P4_PLAN.md](BACKEND_P4_PLAN.md)。
初回配備と再開の具体的手順は [P4_TERRAFORM_RUNBOOK.md](P4_TERRAFORM_RUNBOOK.md)。

## 今回の変更：Terraform初回実行準備

過去の424/452/461件は履歴であり、今回の実行結果ではない。
最終の全体検証は通常Python539成功・実DB57除外。専用tempは`.p4-artifacts/tmp-readiness-final-14`。
Frontendはbackend-contract＋contractsの2ファイル116件成功。過去の102件とは実行対象を明記して区別する。
Terraformはbootstrap/dev/test validate成功、service mock5件＋bootstrap mock1件成功。
Ruff check成功・format check64ファイル適合。workflow YAML6ファイル、Memory＋Fake CLI、
Terraform fmt check、git diff --checkも成功。生成S3 backend HCLと実local backend操作も検証済み。
AWS操作・GitHub設定変更・commit/push・依存更新は0。

Frontendの最初の実行はsandboxのspawn EPERMで起動失敗。その後、誤ったfilterで試験0件となったため、
実在する`tests/backend-contract.test.ts tests/contracts.test.ts`を指定して116件を実行した。
0件実行を成功証拠には数えていない。既存Vite警告、LF/CRLF警告、既存pytest cacheの権限警告は保持した。

| 修正対象 | 修正内容 | offline証拠 |
|---|---|---|
| 入力先行検証 | 未知tf.json/override/tfvars、入力競合をcopy前に拒否 | 追加6件の失敗再現→修正。test_p4_bootstrap_stages |
| 認証元 | SDKの短期CredentialをTerraform childへ固定。profile競合拒否 | test_p4_guard |
| bootstrap再開 | inspect/replan、attempt別成果物、承認hash、private review hash | test_p4_bootstrap_stages |
| 移行保全 | backup fsync、local無条件復元廃止、remote一致ならverify、不存在だけ明示resume | test_p4_bootstrap_readback |
| backend構文 | 正しい複数行HCLと、local backendの実init/plan/apply/State検証 | test_generated_s3_backend_is_valid_hcl / test_real_terraform_local_plan_apply_state |
| 資源読戻し | Bucket owner/Region/TLS対象、OIDC URL/aud、Role trust、boundary本文、SES入力 | test_p4_bootstrap_readback |
| manifest v2 | 承認設定と固定仕様から閉鎖状態を照合。v1の不足を補完しない | test_p4_manifest_v2。300以上の必須leafを個別欠落させて拒否確認 |
| CI transport | plan→envelope確定→version指定取得→保存plan apply、改竄・欠落・upload失敗拒否 | test_p4_ci_readiness |
| CI apply中断 | per-plan開始/完了journal。結果不明は再apply禁止、完了後はverifyだけ | test_durable_apply_receipt_controls_retry |
| OIDC初回確認 | AWS認証なしのClaim確認workflow、Token非表示、redirect拒否 | test_p4_ci_readiness / test_p4_oidc |
| IAM | Budgets Describe系の無効Actionを修正、inline policy合計サイズをmock検証 | bootstrap/tests/contract.tftest.hcl、P4_IAM_AUDIT.md |
| 通常試験の境界 | socketとSDK HTTP送信禁止。実Credential client禁止。既存Stubberは合成Credentialのみ | Backend通常suite全体 |

manifest v2の読戻しはLambda、DynamoDB、3 Queue、2 mapping、Scheduler、API Route/integration/JWT/CORS、
Cognito、LogGroup、Alarm、SNS、Budgetを対象とする。AWSの反映待ちは2秒間隔・60秒期限。
不足・不一致・読取り不能は失敗。SNSのPendingConfirmationは通知到達成功と記録しない。
DB保存schema_version=1、公開6 API、T01〜T14、Fake Provider、MSWは変更しない。

### 未実行・外部前提

- Linux ZIP import：ローカルWindowsでは未実行。CIのAWS認証前必須検証。Windows試験で代用しない。
- AWSのbootstrap/dev apply、S3 backendの実移行、IAM実認可・quota・SES：すべてnot_run。
- GitHub Environmentの作成/設定、実OIDC sub確認、短期認証準備、clean mainへの反映：ユーザー承認後の作業。
- 実機が返す値の差、組織SCP、通知先での確認はmockで保証しない。
- ローカル排他は他端末を排除しない。「1台・1人、他端末操作禁止」が実行条件。
- source/input変更を伴う部分apply修復、Stateがない結果不明apply、remote不一致は自動修復しない。
- 今回対象外：DB追加シナリオ、run観測/hard stop、AS/AU全面実装、負荷・通知・rollback・cleanup。

従って「配備成功」「P4完了」「本番配備可能」とは記載しない。
実行順はrunbookのbootstrap→読戻し→移行→CI保存plan→閉鎖apply。
以後のIAM smoke・実DB・段階的有効化・AU/AS・運用試験には別の実機証拠が必要。

## 実行環境と変更保護

開始時点でP3成果物とP4部分実装に未コミット変更あり。全て保持した。
HEAD: `bc88251bd0c50f92c5daf557eaf28a76981c0e7b`。
検証対象はこのHEADそのものではなく、追加・変更を含むdirty worktreeである。
配備SHA/配備版/対象Account: 未確定・未配備。実値を推測しない。
AWS操作、実OTP送信、GitHub設定変更、コミット/push、新規依存導入は実施していない。

## ローカルで実装・確認したこと

- `.env.local`をGit管理外に設定。許可キーだけを非実行読取りし、Credentialは取り込まない。
- Account/Region、Terraform入力競合、保存planのSHA/入力/State照合。
- API/Worker/Dispatcherの起動口。同Accountの別run混在を3件の失敗で再現後、修正。
- Terraform SES Identityをbootstrapへ集約。通常deploy/test RoleからIdentity変更権限を除去。
- artifact/plan/deploy/test Role分離、dev Subject、東京、予算50/80/100%の定義。
- 実DB fixtureの作成前/削除前STS、作成成功journal、削除待機。
- AWS非接続CI、手動plan/apply、手動実DBworkflowのコード作成。
- 認証E2EにOTP前のAccount/配備読み戻しを接続。
- bootstrapのlocal State作成→AWS資源読戻し→version付きS3への移行実行口を追加。
  二重明示Gate、clean main、段階別Account Guard、移行前backupを実装。
  旧実装の失敗時local State自動復元は廃止し、backup保全と明示再開へ変更した。

## 過去の実行履歴（今回の結果は冒頭を参照）

| 検証 | 状態 | 結果と限界 |
|---|---|---|
| P4 Guard初回 | 失敗→成功 | 実装前import失敗を確認。実装後22件成功 |
| 通常Python | 成功 | 当時424成功、実DB57除外。bootstrap移行実行口追加時の基準 |
| 実DB収集 | 成功 | 57件収集のみ。AWS試験0件 |
| 同Account別run設定 | 失敗→成功 | 3件が修正前に拒否されず失敗。修正後Runtime18件成功 |
| GitHub branch制限 | 成功 | ローカルfixture12件。実GitHub設定の証拠ではない |
| Frontend共通契約 | 成功 | 102件。sandbox EPERM後、同じコマンドを権限付きで実行 |
| CLI | 成功 | Memory/Fakeデモ完走 |
| Terraform validate | 成功 | bootstrap/dev/test。既存hash_key/range_key非推奨警告あり |
| Terraform mock | 成功 | 5件。予算3閾値/別Region SES拒否等。AWS非接続 |
| workflow YAML | 成功 | 既存js-yamlで構文読取り。GitHub実行は未実施 |
| Ruff check/format | 成功 | 管理対象src/tests/skills、54ファイル適合 |
| git diff --check | 成功 | LF/CRLFの既存警告は残るが終了0 |
| Linux ZIP import | 未実行 | workflow実装のみ。Windowsの検査で代用しない |
| bootstrap移行unit | 成功 | AWS非接続4件。Gate先行、入力限定、失敗時State復元、Bucket硬化拒否 |

pytestの既存temp領域およびsandbox内作成領域でアクセス拒否があり、専用tempを作成して
権限付きで試験した。既存cache削除、依存変更、試験除外の緩和は行っていない。
Vite将来configLoader警告、LF/CRLF警告は抑制・変換していない。

## 過去の未完了記録（以下は各記録時点の状態）

### 2026-09-14 bootstrap段階分離

- CLIをplan/apply/migrate/verifyへ分割。planはapplyしない。
- 保存planをソースSHA・Terraform版・入力・全tf設定・lockのhashに結合。
- applyはレビューhash必須。送信前にfsync付きattempt記録を作り、失敗後の再applyを拒否。
- migrateはapply完了記録を要求。移行attempt後は再移行せずverifyで確認する。
- verifyは同じreceipt内容なら繰返し可能。backend宣言の差し替えを拒否。
- 同一workspaceのbootstrap操作を排他ファイルで直列化。強制停止時の残存lockは自動解除しない。
- 今回通常Python461成功、実DB57除外。新規stage試験9件。AWS操作0。

制限: ローカル排他は別hostの操作を排除しない。applyの部分成功・応答喪失後は
自動修復/再applyを提供せず、停止して監査を必要とする。移行試行後にremote未作成の場合の
再開も未実装。段階別CLIの追加をbootstrap全体完成とは扱わない。

### 継続実装（2026-09-13、詳細計画A〜H）

通常Pythonは今回452成功・実DB57除外。前回424成功から28件追加。
通常tempでアクセス拒否を再現後、専用tempで権限付き再実行した。
AWS操作、実OTP、GitHub変更、依存更新、commit/pushは0。

- 認証E2EとOIDC認証に認証前の実行ゲートを追加。
- Terraformのログ・外部data directory指定を拒否し、bootstrapのTF_VAR競合を上書き前に拒否。
- S3 artifact取得の応答VersionIdを要求VersionIdと照合。
- bootstrap移行前にSTS、Bucket所有者・Region・硬化設定・移行先不在を確認。
  403やスロットルを不存在扱いしない。既存Stateがあれば移行しない。
- receipt用StateをVersionId指定で取得し、応答VersionId・暗号化・outputsを含む内容を照合。
- evidence.pyに許可フィールド、固定失敗分類、必須試験不足・別run混在・cleanup失敗の拒否を追加。
  各実行器への接続は未完了。

前回の「bootstrap実行口は実装済み」という記述は部分実装を指す。
段階別plan/apply/migrate/verify、保存planレビュー、再開journal、並行移行排除、
OIDC/IAM/SESの完全読戻し、移行失敗後の安全な再開は未実装。
事前不在確認だけでは並行書込みを排除できないため、現実装を初回実行可能とは扱わない。
詳細計画A〜Hの全体は未完了。以下の残作業も継続する。

以下は**当時の実装残作業**。1〜3は今回の初回配備準備として補修・試験を追加した。
4〜7は今回対象外であり、引き続き単なるAWS実行待ちと表記しない。

1. bootstrap段階別実行口・再開・並行操作排除と初回OIDC Claim確認手順の完成。その後のAWS実行。
2. 保存planの非数値差分の限定閲覧手順、CI制御の成功系/失敗系を網羅した試験。
   数値/真偽値の許可リストによる差分要約は実装済み。
3. 全配備設定の読戻し、IAM/監視仕様との完全照合。
4. DB-01〜20の既存57件に不足する個別シナリオ。
5. run専用観測Table、hard stop試験ZIP、AS-01〜18の実行器。
6. AU全項目、費用推計、監視通知試験、負荷、rollback/再構築/限定cleanup実行器。
7. R01〜22/C01〜15の項目別実行証拠行。

AWS実DB、Streams/SQS/Scheduler、OTP/JWT、IAM、Alarm通知、quota/SES、実負荷はすべて未実行。
P4実装完了・P4完了・本番配備可能とは扱わない。
