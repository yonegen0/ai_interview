# 正式dev Planの承認境界と期限

この文書とコード修正はAWS実行承認ではない。認証・承認制御の変更はレビュー対象HEADで
Draft PRに留める。mainへ反映する承認を別途得た後、実際のmain SHAを固定した新しい
承認資料と全文SHA-256を作る。過去の承認、期限、Run、Bootstrap Applyは再利用しない。

## 承認資料のbinding

workflow_dispatchの`plan_approval_package`には承認資料の正確なUTF-8全文を渡す。
`plan_approval_sha256`はその全文bytesのSHA-256、`plan_approval_expires_at`は資料内の
`expires_at_utc`と文字列まで同一とする。資料は1組だけの
`P4_PLAN_AUTHORIZATION_START`/`P4_PLAN_AUTHORIZATION_END`マーカー内にJSONを持つ。
JSONの重複key、欠損、無効日時、非UTC timezone、hash・入力・source・scope不一致は拒否する。
`execution_ready=false`のレビュー用資料は実行拒否される。期限延長、main変更、操作範囲変更は
必ず新しい資料全文とhashを必要とし、実行中の差替えも拒否する。

期限はタイムゾーン付きUTC（`YYYY-MM-DDTHH:MM:SSZ`または`+00:00`）とし、資料の値が
正式な基準である。時刻が期限と一致した瞬間から拒否する。UTC観測時刻とmonotonic経過時間の
遅い方を使い、時刻の巻戻しで有効期間を延ばさない。deployment job最初のstep、認証前、
Terraform実行前、各Put前、各処理の完了時に検証する。55分job timeoutは維持する。

## OIDCとSTSを区別した数量

|対象Role|GitHub OIDC token HTTP取得|STS AssumeRoleWithWebIdentity|
|---|---:|---:|
|`ai-interview-ci-plan`|最大3回|最大3回|
|`ai-interview-ci-artifact`|最大2回|最大2回|
|deploy/test/指定外Role|0|0|

各上限はこの1つの承認hash・最初の新規workflow RunId・Attempt 1全体に適用する。
成功数ではなく送信試行数を、送信前にfsync済みjournalへ書く。失敗・timeoutも消費し、
その場でterminal停止する。未使用枠が残っていても認証失敗を再試行しない。
OIDC HTTPはredirectなし/timeout15秒、STSはDurationSeconds3600/東京endpoint/SDK試行1回。
issuer/audience/immutable subject/repository/dev/ref/main SHAを検証し、STS応答の厳密な
assumed-role ARN・一時資格の完全性・有効期限も照合する。token/資格はメモリだけに保持する。
OperatorのSSO CreateToken/GetRoleCredentials、AssumeRole/GetSessionToken、provider fallback、
暗黙の資格更新は0。CI開始時のprofile/WebIdentity/container/static資格/endpoint上書きを拒否する。
Python GetCallerIdentityは既存の正常経路7回（5回のRole取得後＋Terraform側2回）を維持する。
Terraform backend/providerのidentity読取りは別であり、全AWS読取り数を7回とは表示しない。

## 再実行拒否とjournal

run-nameは`P4 plan approval-<承認資料全文SHA>`。GitHubのworkflow_dispatch Run履歴を
status/source SHAで絞らず全件照合し、そのhashの最初のRunだけにbindingする。
先行失敗Run、queued Runも消費済みとする。Attempt 2、別Run、同じprocessでの再初期化、
同じlocal journal namespaceでの再起動を拒否する。履歴欠損・ページ重複・件数変化・
1000件制限到達はfail-closed。承認Runの削除・名称変更による消費記録破壊は禁止する。
dispatch前のOperator側独立journalにもdispatch-startedを1回だけ永続記録し、結果不明なら
追加dispatchを行わない。GitHub履歴確認はGETのみで、承認パッケージにも許可操作として含める。

CIは実行開始・OIDC/STS別の回数・RequestId・期限拒否箇所・固定safe reason・例外型を
private permissionの連番JSONへ追記する。raw exception、資格、メール、State、Terraform出力を
journalやCIログへコピーしない。always stepで安全なjournalだけをGitHub Actions Artifactへ
30日保持する。この証跡保存は新規AWS操作ではなく、期限後も許可する独立した保存工程。
State・生のPlan・raw reviewを公開Artifactに含めない。

## 長時間処理と安全な停止

認証OIDC20秒/STS25秒、Put＋exact VersionId readback60秒、build各command600秒、
init300秒、正式Plan1200秒を開始時の残り時間に照合する。subprocessはさらに通常停止用
120秒を確保し、1秒ごとに期限と処理budgetを監視する。git確認やshowなども期限検証する。
job開始時のmonotonic markerを引き継ぎ、checkout/setupも55分に含める。52分で新規工程を
止め、残り3分を通常停止と安全なjournal保存に確保する。Terraform全工程の開始には
32分の残り時間を要求する。
長時間処理の残り時間不足は開始前に拒否する。正式Plan開始記録は1回だけで、完了応答不明や
途中期限切れでは後続認証・Put・再Planへ進まない。各Putは固定bucket/key、1key1試行、全体6回、
envelope最後を強制する。これは通常のdev `.tflock`取得・自分の通常解放とは別枠である。

停止時はTerraformへSIGINTを1回だけ送り、最大120秒の通常終了を待つ。SIGKILL、2回目SIGINT、
force-unlock、lock手動削除、State修復、再Planをしない。既に開始した処理の通常lock解放だけを
cleanupとして許容し、期限後に新しいPlan/lock取得/Artifact Putを開始する権限はない。
in-flight要求の完了や応答不明は成功とみなさない。正常終了を確認できない場合、外側55分timeout
で終了してもState/lockはunknownであり、別の承認範囲内read-only診断まで停止する。
SIGINT後の終了コードだけでlockなし/PASSとは認定しない。保存済みjournal・S3のpartial object・
Planファイルは削除せず、事後検証ができない条件を未確認として報告する。

GitHub Gate=false復帰も承認期限内に行う。期限後のfalse書込みを暗黙に承認しない。
期限内に閉鎖できない場合はGate状態をunknown/未閉鎖と報告し、新しい明示承認を必要とする。
Apply/Enablement/Closureの既存承認、Bootstrap consumed ledger、課金・IAM境界を拡張しない。
