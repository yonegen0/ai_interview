# Gate B Environment App認証とPlan003の承認前準備

2026-10-27 JST。コード提案・オフライン検証の記録。運用設定変更やAWS実行の承認ではない。

## 判定と観測

- main: `59e76ab110f01b8fa7317b102bb2bebb2a9d7a4a`。
- PR62: `f8adfaeb0519f52b937d93b04270518b61f71257`、APPROVE相当。
  finite diagnosticsとprocess観測を独立確認。既存のBackend/Frontend/P4 CIはSUCCESS。
  認証方式・readiness条件を変更しない診断PRであり、403解消とは別。
- PR61: `bb65cb8e42b56a7aff6c28d4999726d5913c60f0`、APPROVE相当。
  generate開始時の入力を保存待ちより前に固定するため、保存中の編集が自動採用で消えない。
  saveStarが送るsnapshot、generationのexpectedVersion、結果待機の条件と整合する。
  修正2ファイルと既存SUCCESS CIを確認し、変更のないFrontend試験は再実行していない。
- 現operator資格によるGitHub読取りでは、両Environmentのreadiness4項目は全て`false`。
  これはApp tokenのcapability検証ではない。既存job tokenの403は引き続き未解消。
- `P4_ENV_APP_PRIVATE_KEY`は両EnvironmentのSecret名一覧にない。
  Secret値・秘密鍵は読んでいない。repository variables一覧はHTTP403で未確認。
- 元Apply正常終了UNKNOWN、Plan002直接拒否条件UNKNOWNを維持。journal再復号0。
- Plan003 NOT_READY、Gate B復旧途中、公開NOT_READY。AWS接続・変更0、実AI0。

## 最小変更

`github_control.py`に専用`P4_ENV_READ_TOKEN`を追加。既存`GH_TOKEN`は
履歴・main・Environment保護等の既存API処理用に保持する。代替token、retry、redirectはない。
専用tokenは対象固定のvariables GETと、capability用のinstallation repositories GETだけで使う。
Git/Terraform子プロセスへ専用tokenを渡さない。

variables APIは`per_page=30`、最大10ページ/300件/各応答1MiB。
全ページでtotal_countが同じ非負整数であること、各ページの期待件数、最終取得件数を確認。
同一名（大文字小文字の差を含む）、JSON object key重複、不正な構造・型・過剰件数・欠落ページを拒否。
必須2変数の欠落・値不一致、片側だけ成功した結果を合格にしない。
変数のname/valueを検証し、利用しないAPI metadataは保存・出力しない。

Planではdev-planの`P4_STANDARD_READY`/`P4_AWS_EXECUTION_READY`が両方true、
dev-applyの同2項目が両方false。Applyは逆。条件を緩和して403を回避しない。
401/403/404/429/5xx/redirectは固定reasonで分類し、例外本文・URL・header・tokenを公開しない。

標準Plan/ApplyではAWS role取得前にrepository一覧（対象ID/名前1件だけ）と両readinessを検証。
既存check_liveの実行前後のreadiness再読取りも同じ厳格処理へ接続する。
GitHub-only検証に成功しても、State・実AWS・Terraform・実効IAMの成功は証明しない。

## 公式Actionと期限

`actions/create-github-app-token` v3.3.0を
`64ab729a6294000f5aa4a4bc0b73d1f32bc45510`へ固定。
公式release/tagの一致、GitHub commit verificationの`verified=true/reason=valid`、
action.ymlと発行実装を確認した。owner=`yonegen0`、repositories=`ai_interview`、
permission-environments=`read`を明示し、他の追加permission入力は設定しない。
Metadata(read)はGitHubが付与する必須権限。ジョブ完了時の標準revokeを維持する。

installation tokenの公式寿命は1時間。Actionが公開するoutputはtoken/installation-id/app-slugで、
expires_atは公開しない。このため発行Action直前の時刻から55分を保守的なローカル期限とし、
HTTP用30秒を残して各要求を拒否する。発行に時間が掛かるほど利用可能時間が短くなる。
サーバー側の期限切れ/失効は401で拒否。期限延長・自動更新・fallbackはない。
このローカル期限をGitHubの実expires_atを取得した証拠として扱わない。

最小権限は発行Actionの明示permissionとApp設定で固定する。
installation repositories応答はtokenのrepository範囲を確認できるが、granular permission全体の
introspectionではない。App自体の過剰権限や余分なinstallationは設定画面で拒否する。
API versionは既存の無指定時defaultと同じ`2022-11-28`を明示し、外部API版の移行は行わない。

## 検証

- Python3.14.9 / uv0.13.5 / 既存uv.lock。依存更新0。
- 重点回帰236件PASS（toolchain契約2件を含む）。既存の承認hash/期限/再利用、State identity、subprocess起動失敗・
  非正常終了・終了UNKNOWN、StageだけのPlan監査を再利用。
- 新規試験はApp token分離、期限とページ間失効、scope、pagination、HTTP/redirect、
  malformed JSON、両readiness、AWS到達前拒否、子プロセスへのtoken非継承に限定。
- Backend全Ruff check/format PASS。変更3workflowはactionlint1.7.12 PASS。
- 初回CIは、既存toolchain契約がsetup-uvをworkflow内1個に限定していたため失敗。
  GitHub-only/OIDCの2個を許可し、各setup blockの固定SHA・uv/Python版を個別照合する形に修正した。
- 新HEADの真正CIはPRチェックを正本とし、実GitHub App検証は未実施。

## まとめて承認・設定する対象（未実行）

1. PR62を指定HEADでmainへ通常merge。その後、このPRのbaseを最新mainへ変更し、
   差分・HEAD・CI・保護条件を再確認して本提案を通常mergeする。
   認証を含む運用workflow変更の承認であり、Ruleset/branch保護の変更やbypassは含まない。
2. GitHub Settings → Developer settings → GitHub Appsで専用Appを作成する。
   Webhookは無効、Repository permissionsはEnvironments(read)と必須Metadata(read)だけ。
   Install App → Only select repositories → `yonegen0/ai_interview`だけを選択。
   他repository、organization/account権限、書込み権限は付与しない。
3. Repository Settings → Environments → `dev-plan`と`dev-apply`の各画面で、
   Environment variable `P4_ENV_APP_CLIENT_ID`、Environment secret `P4_ENV_APP_PRIVATE_KEY`を登録。
   Client IDとApp private keyは本人が設定画面へ直接入力する。チャットへ秘密値を送らない。
   Keyをリポジトリへ置かず、既存Secretを上書きしない。
4. GitHub-only検証1回（attempt1、10分上限）の承認：
   `dev-plan`のreadiness2項目だけを一時trueへ設定し、dev-applyはfalseのまま確認。
   `p4-standard-qualify.yml`を最新main/source_sha固定、mode=`github-only`、operation=`plan`でdispatch。
   OIDC資格発行権限はなく、AWS Secretを当該stepへ渡さず、Terraform/実AIは起動しない。
   App token発行、対象repository1件、両variables API、readiness一致を実測する。
   不正応答の拒否はオフライン試験の証拠と区別し、実APIへ故意の不正データは書かない。
5. 成否にかかわらずdev-planの2項目をfalseへ復帰し、両Environment全4項目falseを読み戻す。
   readiness書込みは最大4回（true2回・復帰false2回）。Secret/Client ID登録は各Environment各1件。
   GitHub-only capability GETは最大21回（repository1 + variables最大10ページ×2）。
   token発行Actionの5xx/通信障害時の内部retryは公式実装どおり最大4試行で、別tokenへfallbackしない。
   失敗時の再dispatch・rerun、権限追加、別認証による回避は今回の1回承認に含めない。

本人設定後、承認範囲内でCodexが通常merge、最終SHA照合、GitHub-only実測、
readiness復帰・読戻し、Plan003承認パッケージの最終準備まで進める。
この承認依頼にTerraform init/plan/apply、AWS監査・State読取り、入口開放は含めない。

## Plan003の実行直前条件

新sourceはmerge前なので未確定。期限・承認hash・run IDを架空に補完した実行用descriptorは作らない。
以下を全て固定し、新規72時間・単回利用の明示承認を得た時点でだけREADYにできる。

| 固定する項目 | 条件・現在の扱い |
| --- | --- |
| 認証・readiness | 上記GitHub-only1回の真正成功証拠。現在は実測待ち |
| source | merge後の最新mainと承認source SHA、workflow SHAが一致 |
| 承認bytes | 新パッケージ全体のSHA-256、UTF-8 bytes、改行を搬送前後で一致させる |
| Secret搬送 | `gh secret set`のstdin末尾CR/LF除去に依存しない。承認対象を最初から末尾改行なしのcanonical bytesで作り、GitHubでの照合まで一致を確認する。承認後の正規化は禁止 |
| 承認消費 | issue/deadlineは新規72h、run/attemptへ紐付け。既存run履歴を全件照合。Plan001/002承認を再利用しない |
| State | 既存State13のlineage/serial/VersionId/hash、snapshot hashをprivate descriptorへ固定。新しいAWS観測は別承認。現AWS実体の証明として流用しない |
| toolchain | Terraform1.14.9 / AWS Provider6.65.0を維持。PR43 HOLD |
| Artifact | 既存bucket/key/VersionId/digest、Lambda bindingを固定。build/upload/Lambda再配備を禁止 |
| Stage | 観測済み4項目beforeと期待6項目afterのliteralを固定。更新1件のみ |
| 入口 | API/Worker/Streams/Scheduler閉鎖を承認範囲内の実readbackで照合 |
| 差分受入 | add0/change1/destroy0/replace0。IAM/State移行/未承認drift/重要unknown/import/move等を拒否 |
| 上限 | 既存SDK512/HTTP512、Terraform Plan20分/job55分、session3600秒、OIDC/STS plan3+artifact2、S3 Put5個を維持。新パッケージでoperator/API/費用上限も明示 |
| 終端 | Plan失敗・process終了UNKNOWN・State/lock不明で再実行しない。新saved Plan専用Applyは別承認 |

元Apply正常終了UNKNOWNを維持する。Gate B後も実Cognito/OTP/JWT接続受入、実AI品質/費用、
30人性能、hosting・公開受入は既存の別承認で確認する。
今回の差分・PR61/62の確認に新しい製品P0/P1の再現はない。既存CIが成功している範囲の
認証・Coaching V2・STAR制限・冪等性・SQS/Workerを無根拠に再監査しない。

## 公式根拠

- [Environment variables API: Environments(read), per_page最大30](https://docs.github.com/en/rest/actions/variables#list-environment-variables)
- [公式Actionの固定版](https://github.com/actions/create-github-app-token/tree/64ab729a6294000f5aa4a4bc0b73d1f32bc45510)
- [token発行実装と期限保存](https://github.com/actions/create-github-app-token/blob/64ab729a6294000f5aa4a4bc0b73d1f32bc45510/lib/main.js)
- [installation tokenによるrepository範囲の取得](https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation)
- [API版のdefaultとサポート方針](https://docs.github.com/en/rest/about-the-rest-api/api-versions)
