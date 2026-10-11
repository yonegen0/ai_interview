# 正式dev Planの承認境界と期限

この文書とコード修正はAWS実行承認ではない。認証・承認制御の変更はレビュー対象HEADで
Draft PRに留める。mainへ反映する承認を別途得た後、実際のmain SHAを固定した新しい
承認資料と全文SHA-256を作る。過去の承認、期限、Run、Bootstrap Applyは再利用しない。

## 承認資料のbinding

承認資料の正確なUTF-8全文はdev Environment Secret `P4_PLAN_APPROVAL_PACKAGE`から読む。
public workflow_dispatchへ全文を渡すinputは廃止し、旧方式へfallbackしない。
`plan_approval_sha256`はその全文bytesのSHA-256、`plan_approval_expires_at`は資料内の
`expires_at_utc`と文字列まで同一とする。資料は1組だけの
`P4_PLAN_AUTHORIZATION_START`/`P4_PLAN_AUTHORIZATION_END`マーカー内にJSONを持つ。
JSONの重複key、欠損、無効日時、非UTC timezone、hash・入力・source・scope不一致は拒否する。
期限から生成する一時session policyのSHAも資料へ固定し、CIで再計算して照合する。
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
Plan用の両Role取得には、期限到達時から全Actionを明示Denyする一時session policyを必須とする。
期限前のAllowは既存Role権限とのintersectionであり、新しいIAM権限を追加しない。
Role/trust/保存policyの変更APIは呼ばない。このsession restrictionも新しい承認資料に含める。
AWSの[session policy仕様](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html)と
[DateGreaterThanEquals仕様](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html)に基づく設計で、実AWSでの有効性は未検証。
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
journalやCIログへコピーしない。詳細journalの平文は公開Artifactへ保存しない。
公開可能な固定summaryと、承認固定recipientへ暗号化したCMSだけを明示pathで30日保持する。
これは新規AWS操作ではなく、期限後も許可する独立した証跡保存工程。
State・生のPlan・raw review・承認全文・秘密鍵はArtifactに含めない。

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
force-unlock、lock手動削除、State修復、再Planをしない。通常lock解放も期限前の120秒reserve内で
行う。期限後に新しいPlan/lock取得/lock解放/Artifact Putを開始する権限はない。
ローカル監視が遅れた場合もsession policyの期限DenyでAWS側の新規副作用を拒否する設計である。
期限を越えた通常解放の例外は作らず、解放未確認・lock残存はunknownとして停止する。
in-flight要求の完了や応答不明は成功とみなさない。正常終了を確認できない場合、外側55分timeout
で終了してもState/lockはunknownであり、別の承認範囲内read-only診断まで停止する。
SIGINT後の終了コードだけでlockなし/PASSとは認定しない。保存済みjournal・S3のpartial object・
Planファイルは削除せず、事後検証ができない条件を未確認として報告する。

GitHub Gate=false復帰も承認期限内に行う。期限後のfalse書込みを暗黙に承認しない。
期限内に閉鎖できない場合はGate状態をunknown/未閉鎖と報告し、新しい明示承認を必要とする。
Apply/Enablement/Closureの既存承認、Bootstrap consumed ledger、課金・IAM境界を拡張しない。

## public repositoryでの証跡・入力保護

GitHub Artifactはrepository read accessの利用者がダウンロードできる。public repoで
`.private.json`の名前、runner chmod、30日retentionは閲覧を制限しない。
[GitHub Artifact仕様](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)。
[Runner実装](https://github.com/actions/runner/blob/main/src/Runner.Worker/Handlers/ScriptHandler.cs)は
runの環境変数を開始ログへ表示するため、private値をvars/dispatch入力/envへ平文で渡さない。
Secret maskingは多層防御であり、private内容をechoしてよいという保証ではない。

|情報|保存・公開範囲|
|---|---|
|資格/token/access key/secret/private key|journal・Git・Artifactに記録しない。復号秘密鍵はrunnerへ渡さない|
|Account/Bucket/Key/RequestId/詳細stage/内部時刻|承認固定recipientに暗号化したjournal。平文はrunner private directoryとOperator限定ACLの証跡だけ|
|承認全文/メール等configuration/OIDC subject|dev Environment Secretsのみ。dispatchは全文SHA/期限/recipient DER SHAだけ。Git反映しない|
|公開summary|schema_versionと固定enum evidence=encrypted/unavailableのみ|
|run名/RunId/source SHA/承認SHA/期限/recipient fingerprint|公開workflow metadataとして許可。秘密や実識別子を埋め込まない|
|暗号化詳細|public Artifactから暗号文は取得可能。recipient秘密鍵を持つOperatorだけが復号する設計|

Planとsaved-plan applyの `AWS_DEV_ACCOUNT_ID`、`P4_OIDC_SUBJECT`、`P4_DEPLOY_INPUTS`も
dev Environment Secretsを使い、同名varsへのfallbackをしない。Applyの明示承認境界は維持する。
ApplyもSecret移行を実行準備の条件とし、既存varsだけでは動作させない。
Secret未設定/不一致・証明書欠損/不一致はAWS前に拒否する。
`evidence_recipient_sha256`を新承認descriptorへ追加し、dispatch `evidence_cert_sha256`と
Secret `P4_PLAN_EVIDENCE_CERT_PEM`のDER SHAを照合する。RSA3072bit以上、承認期限を超える
有効期間、OpenSSL暗号化演習を最初の認証前に検査する。実recipientと秘密鍵保管・復号能力は
将来承認前にOperatorが確認する。テスト用鍵や過去fingerprintを実行に転用しない。

[OpenSSL CMS](https://docs.openssl.org/3.5/man1/openssl-cms/)のAES-256-GCM AuthEnvelopedDataと
RSA-OAEP/SHA256を使う。証明書fingerprintでrecipientを固定し、CA/ネットワークへ接続しない。
CMSは`-keyid`を必須とし、issuer DN/serialを公開しない。SubjectKeyIdentifierは公開RSA鍵の
PKCS#1 DERから導く20byte SHA1と一致することを検査し、任意の機密payloadを拒否する。
この鍵識別子だけは暗号文metadataとして公開可能。証明書のbindingは別のSHA256で行う。
暗号化は連番journalとjob-start記録だけ。symlink/過大/不正JSONは拒否し、入力原本を
削除・上書きしない。公開uploadはsummary.json/journal.cmsと、checkout/setup失敗時だけの
固定fallback summaryの明示3pathだけ。広いglobは使わない。依存なしのalways stepでfallbackを
保存するが、checkout/setup失敗時の詳細markerの暗号化回収は保証しない。
暗号化失敗/timeoutでは固定unavailable summaryだけを保存し、詳細証跡保全は未確認・失敗と報告。
平文fallback、再AWS、再dispatch、再Planは禁止。runner消滅後の平文回収は保証できないため、
暗号化失敗を成功扱いしない。新規AWS書込みは追加しない。

Secretsの作成/更新、recipient登録、実runの公開露出・暗号化/復号確認は今回実施しない。
merge承認には含めず、将来の新Plan資料で固定内容/hash・各Secret更新回数・期限・事後検証を
明示承認する。旧未承認全文SHAや旧期限は使用不可。merge後の実main/CI/Artifactを確認してから
新資料/新期限/全文SHA/recipientを確定し、独立レビューとユーザーのPlan承認を得る。
