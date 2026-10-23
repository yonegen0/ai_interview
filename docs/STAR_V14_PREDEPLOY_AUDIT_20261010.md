# STAR Ver.1.4 独立監査・配備前検証 — 2026-10-10

監査ステータス: `STAR_V14_PREDEPLOY_REVIEW_VERIFIED_PENDING_APPLY_APPROVAL`

オフライン品質判定 **PASS**。P0未解決0件、配備を妨げるコード上のP1未解決0件。新たに見つけたP1 7件とP2 1件を修正し、独立回帰を実行した。これはAWS配備・実AI接続の承認ではない。実AWSへの配備は、独立したbootstrap maintenanceのBLOCKED事項と、対象成果物・差分への明示承認が残るため **BLOCKED**。

## 対象・Git・保全

- 監査対象実装: `98e0a0fa8e9a89ef8ccf8e65b255a97ecbff7803`、branch `codex/star-assist-v14-offline-20261010`。
- 実装の親/main基準: `bc0919e13477f4d86609e1c7ed51590e118a8fd2`。元70ファイルのcommit、manifest、実装報告書は一致。
- 監査branch: `codex/star-v14-predeploy-audit-20261010`。cleanだった既存の独立worktree `.p4-artifacts/star-assist-v14-offline-20261010/source` を再利用し、専用branchへ切替。元branchのref/commitは維持。
- 修正・追加は11ファイル。最終ローカルcommitの完全SHAとclean状態は新private領域の `commit-result.private.json` に保存し、最終応答に記載する。amend/push/PR作成/main mergeは実施しない。
- 元作業ツリーの21ファイルのSHA/サイズ、binary diff、HEADを再照合した。元STAR証跡82件に加え、既存11 indexの合計2039 entriesもSHA/サイズ一致。重複参照を含む件数であり、2039個の独立ファイルという意味ではない。
- saved Plan、State、journal、正式Artifact、旧index、既存lockfileを変更していない。元作業ツリーのSTAR実装結果報告書もハッシュ一致。
- 新証跡は `.p4-artifacts/star-v14-predeploy-audit-20261010`。旧exclusive作成スクリプトは再実行せず、専用runner・新規ログ・新規一時ディレクトリを使用した。
- GitHub main/PR #5および現在のAWS/Stateは今回照会していない。以下のbootstrap状態はローカル保存証跡に基づく。

## 問題と修正

|ID|重大度|原因・修正|独立確認|
|---|---|---|---|
|A01|P1|STAR反映時、通常下書きの期限が先に読んだSTAR期限を上書き。`bound_expiry`で全期限の最短値を維持|境界直前に開始→commit直前に失効、旧200→修正後409、本文・application不変|
|A02|P1|設定の世代CASは読取り時の期限だけを検査し、失効をまたいで旧世代を延長できた。commit境界も検査|旧200→修正後409、期限切れ設定はnull|
|A03|P1|正式送信のapplication期限がcommitまで保護されず、CAS再試行では固定受付時刻を再使用。実時計で検査しcommit windowを設定|旧202→修正後404、Evaluation/Attempt未作成。成功済み同keyの再現は維持|
|A04|P1|通常回答のdirtyだけで初期復元を判定し、GET待ちのSTAR編集を旧保存版で消していた。通常/STARの復元判定を分離|旧保存メモが遅着しても新入力を保持し競合を表示|
|A05|P1|preferencesがdraftsより先に戻ると、initialized ref変更がeffect再実行を起こさず未選択のまま。drafts取得を依存に追加|先着preferencesのカテゴリを正しく復元|
|A06|P1|空のdrafts GETで入力中の値を保存済みbaselineにしてしまい、自動保存を抑止。baselineはserver実体/空の値を使用|GET待ちに入力したSTARメモが初期取得後に自動保存される|
|A07|P1|STAR終端を既存評価用監視wrapperが認識せず、OutcomeUnknownおよび滞留指標が欠落。commit済み復旧結果・Worker callback・STAR work observationを接続|Worker timeout/Recoveryで既存OutcomeUnknownを発行、正常な再Recoveryで重複なし、PendingAge/ExpiredLease/DeadlineOverdueを確認|
|A08|P2|E2EのPNGが前回private証跡と同じ保存先だった。Playwrightの試験別outputPathへ変更|37 E2E成功後も旧82件のハッシュ一致。新3幅PNGを新証跡へコピー|

P0検出0件、P1検出7件/修正7件/未解決0件、P2検出1件/修正1件/未解決0件。A01–A03とA04–A05、A07は修正前のFAILログを保存した。A06はコードから特定し、未保存入力の回帰試験を追加した。環境エラー/初期FAILログを最終PASSへ書き換えていない。

commit windowはクライアント側の送信直前検査であり、DynamoDBにサーバー時計の条件式を追加したものではない。送信後のサービス処理までに期限をまたぐ可能性は残り、実AWSでは境界試験が必要。GETは実時計で失効を拒否する。

### 変更したファイル

|ファイル|目的|
|---|---|
|`backend/src/interview_backend/star_assist/repository.py`|複合期限/正式applicationの保護、commit済みRecovery結果、STAR滞留観測|
|`backend/src/interview_backend/star_assist/models.py`|保存・APIへ出さないRecovery観測結果型|
|`backend/src/interview_backend/star_assist/worker.py`|結果不明の既存metric callback|
|`backend/src/interview_backend/evaluation/worker.py`|STARへ既存callbackを渡す|
|`backend/src/interview_backend/repositories/domain.py`|STAR work observationへ分岐|
|`backend/src/interview_backend/observability.py`|STAR Recoveryを既存OutcomeUnknownへ接続|
|`backend/tests/unit/test_star_assist.py`|追加13ケース。期限3、送信/保存2、本人分離1、不正出力4、監視3|
|`frontend/src/features/starAssist/hooks/useStarWorkspace.ts`|独立dirty検査、preferences復元、未保存baseline|
|`frontend/tests/star-workspace-audit.test.tsx`|取得順序と読込み中編集の3ケース|
|`frontend/tests/e2e/star-assist.spec.ts`|既存PNG上書き防止|
|`docs/STAR_V14_PREDEPLOY_AUDIT_20261010.md`|本監査報告|

依存/ロック、Terraform、workflow、採点ロジック、回答Body/fingerprintは今回変更していない。

## 仕様・セキュリティ・互換性の追跡

元T01–T24は [実装検証報告](STAR_V14_OFFLINE_VERIFICATION.md) のコード対応表を維持する。今回は報告件数の引継ぎに加え、以下の試験を独立実行した。

|要求|実装位置|試験/確認|結果・限界|
|---|---|---|---|
|本人/質問/回答段階|`star_assist/repository.py::_star_context_spec`、`useAnswerOperation.ts`|T02/T14/T20、追加本人分離/遅延GET|PASS。Session質問snapshotと起点Attempt/Evaluationを使用|
|応募先10カテゴリ/業界/企業14日|models、preferences CAS、workspace|T03/T04、A02/A05|PASS。別owner入力を受けず、閲覧で延長しない|
|STAR7日/通常14日|draft CRUD、codec expiresAt|T03/T08、A01/A03|PASS。物理削除は未検証|
|空欄拒否/情報不足/3案|FakeStarProvider、Pydantic/Zod|T01/T21、追加不正Provider出力4ケース|PASS。Aがなければ試行後needs_information。目標150–220はUI目安、Fakeは入力事実を並べ替えるだけ|
|3案個別編集/選択/明示反映|StarCandidateFields、workspace、star_apply|T15/T21/T22、37 E2E|PASS。選択前編集/切替保持/確認Dialog/Escape/反映中入力|
|保存1秒/復元/競合/応答不明|workspace、receipt、IndexedDB V4|T05/T06/T07/T19/T20/T23、追加画面3ケース|PASS。本人scope、固定key/payload、最新版との比較、入力保持|
|正式送信後の下書き復活防止|既存受付transaction＋star_complete_answer|T08/T09/T10、追加inflight保存2ケース|PASS。保存開始→正式受付→遅延到着409。旧本文復活なし、Evaluation/Attempt各1件|
|本人分離/認証|owner PK、JWT routes、ApiEntry|T02、追加他owner generation/PUT/quota/preferences、既存runtime/認証回帰|PASS。署名不正JWTはGateway責務で実Cognito試験は未実施|
|20/600/JST月/同文脈1生成|atomic quota/STARTED/lease|T11/T12/T13|PASS。同本人並列/同key/別key、複数本人の最後1枠、月境界、予約返却/消費、結果不明で再Provider呼出しなし|
|出力/ログ安全|strict schema、validate_fake_facts、安全ログ|T01/T24、追加不正出力/監視試験|PASS。創作・401 codepoints・unknown field・欠落・style不整合を拒否。本文/JWTを新metricへ出さない|
|Coaching V2/V1|既存provider/coaching/repository、recovery|全pytest、Frontend/Storybook、coaching-v2 E2E|PASS。30点/400 codepoints/0・1・2減点/最大3回/累積/初回ID/4操作/本文なしretry_evaluation/V1 100点500 UTF-16維持|
|配送・Recovery・監視|Dispatch/events/Worker/4 partition rotation|T17/T18、SDK Stubber、A07|PASS。下書き/REMOVEを配送しない、保存Dispatchとの種別照合、cursor/時間予算保持|

375/768/1280pxの新PNGを独立目視確認した。横overflow、3案の配置、通常回答欄と正式送信、キーボードTab/EscapeはE2Eでも確認。実端末/実ユーザーのアクセシビリティ保証ではない。

Fakeはメモ中の命令を実行せず、与えられた事実の並べ替えしか行わない。構造/創作拒否の成功は、実モデルのprompt injection耐性・カテゴリ適合性・自然さの評価を代替しない。

## 独立実行結果

|コマンド（対象cwd）|今回の最終結果|前回との差|
|---|---|---|
|Backend `python -B -m ruff check .`|PASS|維持|
|`python -B -m ruff format --check src tests skills`|143ファイル PASS|維持|
|`pytest -q --tb=short -p no:cacheprovider --basetemp <fresh> -m "not dynamodb and not aws_e2e"`|**1514 PASS / 1 SKIP / 57 deselected**|1501＋追加13|
|`python -B -m interview_backend.demo`|V1 Memory/Fake PASS|維持|
|Frontend `npm run lint` / `npm run typecheck`|PASS、lint error/warning 0|維持|
|`npm test`|**665 PASS**、64 files、unit275＋Storybook browser390|662＋追加3|
|`npm run build` / `npm run build:mock` / `npm run build-storybook`|すべてPASS|維持|
|`npm run test:e2e`|**37 PASS**|既存全回帰。補足5件はこの全体に含まれるため別再実行/加算なし|
|`terraform fmt -check -recursive terraform`|PASS|Terraform変更なし|
|隔離コピー `init -backend=false -input=false -lockfile=readonly` / `validate`|4 roots PASS|同じ公式ZIP/元lockのzh照合、filesystem mirrorだけ|
|隔離コピー `terraform test -no-color`|**service48＋bootstrap4＝52 PASS / 0 FAIL**|全runでmock_provider。正式remote Planではない|
|`git diff --check`|PASS|維持|

SKIPは既存Windows symlink権限試験。57除外は明示禁止の実DynamoDB/AWS E2E。初回のsandbox pytestは新tempアクセス拒否、Vitestはspawn EPERMで完了しなかった。新ログへ権限を適切に分離して再実行した。追加テストのRuff整形失敗も修正・保存済み。成功結果は最終runだけを示す。

試験子プロセスからAWS/TF/P4/OpenAI/INTERVIEW/公開API設定の環境変数を除去した。Backend autouse fixtureはsocket/SDK送信を拒否し、SDK Stubberはsynthetic資格情報だけ。FrontendはローカルMSW/Chromiumと明示Mockビルド。Terraformはsource-only隔離コピー、空AWS config、backend無効、公式ZIPのfilesystem mirror。資格情報・個人情報を新資料へ転記していない。

## AWS/Terraform/IAMのソース監査

元70ファイルに含まれる候補差分は16 STAR JWT route、PUTおよび補助ヘッダーCORS、API transactionのUSER ConditionCheckと正確な `SYSTEM#STAR_QUOTA`へのPut/ConditionCheck、既定falseの任意TTL。既存ADMINのkey-only読取り制限を維持。GetItemの既存権限は変えていないため、IAMだけで個々の本人を分離するものではなく、owner検証とPKで分離する。

新DynamoDBレコードには独立PK/SK/WorkIndexを使用。Streams filterはDispatchのみ、Worker MaximumConcurrency=2、batch_size=1、512MB/x86_64/python3.14、Worker60秒/Provider40秒/ジョブdeadline15分を維持。API throttleはrate20/burst30。Lambda/SQS/Streams/Schedulerの4有効化フラグとprovider locksは変更していない。

A07は既存AIInterview namespace/Project・Environment・Component dimension/OutcomeUnknown/滞留metricを再使用。新Alarm、metric filter、dashboard、dimensionは追加しない。既存OutcomeUnknown alarmのworker/dispatcherを合算する式に整合する。telemetryはbest effortであり、業務transactionとは別。実CloudWatchの発火/到達保証はAWS検証が必要。

TTL既定falseでもAPI失効を検査する。期限後の物理削除を保証していない。[AWS TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) の非同期削除と、API期限を区別する。TTLを有効にする前には既存データの属性・削除影響を実環境で承認付き確認する。

## 性能・費用の想定（実測/承認上限ではない）

30本人Memory/MSWケースは今回のunit全体でもPASSした。前回343.6msを今回のAWS性能値として転用しない。正式performance gateは変更していない。

主なボトルネックは次のとおり。

1. Worker2枠を評価/STARが共有。30生成だけでも、平均d秒なら最後のwaveまで概ね15d秒。d=40秒の単純計算は600秒で、他評価・cold start・配送/retryは別に加わる。実AI timeout/15分deadlineとの余裕を検証する。
2. 生成中GETは1秒周期。30人ならpollだけで約30RPSとなり、既存HTTP API rate20/burst30に達する。dirty入力の自動保存も加わるため、429と利用者の待ち時間を実AWSで測る必要がある。未変更保存0を維持し、根拠なくthrottle/concurrencyを変更しない。
3. global quotaは月1レコードでCAS競合する。各要求はbounded retry/5秒予算を使う。小規模並列Memory成功をDynamoDB競合の保証にしない。
4. CAS依存の強整合Get、transaction、四領域Recovery、IndexedDB全snapshotの解析/cloneが負荷に寄与する。Lambda cold startとGSI反映遅延は未測定。

既存AWS資源を再利用し、今回のソース変更では新しい常駐compute/PC/NAT/専用テーブルを追加しない。ただしIAM/routeが無料でも、API/Lambda/DDB/SQS/ログ・custom metrics/既存validation Alarm/保存容量の料金は増え得る。TTL無効なら期限切れ本文の物理保存量も蓄積する。生成回数600は保存/GET回数やAWS費用の上限ではない。

概算式: API=Nreq×地域単価、Lambda=Σ(0.5GB×秒数)×地域GB-s単価＋request料金、DDB=transaction/strong-read/KB丸め/ConditionCheck/再試行を含むrequest units×地域単価＋GB-month/GSI、SQS=64KB単位の操作数×地域単価、CloudWatch=ログ量/保持/metric/Alarm-hour。[AWS取引仕様](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) はtransactionで準備・commitの両方のcapacity消費を説明する。[Lambda料金](https://aws.amazon.com/lambda/pricing/)、[HTTP API料金](https://aws.amazon.com/api-gateway/pricing/)、[DDB料金](https://aws.amazon.com/dynamodb/pricing/)、[SQS料金](https://aws.amazon.com/sqs/pricing/) を参照。

公式Lambda料金例の$0.0000166667/GB-sを仮置きしたWorker600回分だけなら、平均1/10/40秒で約$0.005/$0.05/$0.20＋request約$0.00012。これは他Lambda/GET/DB/queue/ログ/税/地域差/無料枠を含まない説明用計算で、東京の総予算ではない。既存runbookの14 validation Alarmはgross$1.40/月相当の時間比例であり、custom metricsとは別。東京の正確な単価・総AWS費用・無料枠残量は配備承認資料で固定する。

実AIについては2026-10-10に[GPT-6 Luna公式モデル資料](https://developers.openai.com/api/docs/models/gpt-6-luna) と[料金](https://developers.openai.com/api/docs/pricing)を読取り確認した。公開Standard/short-contextの参考単価はinput $0.10/output $0.50 per 1M tokens。このプロジェクト/アカウントの利用権、モデル実応答、WIF互換性、生成品質を確認したものではない。候補IDは `gpt-6-luna` を維持する。

600回の参考計算は `600 × (Tin×0.10 + Tout×0.50)/1,000,000 USD`。Tin/Toutにはsystem/schema/Japanese token化/課金対象reasoningを含める。各1000/500なら$0.21、2000/1000なら$0.42、4000/2000なら$0.84。いずれも仮定値であり、文字数からtoken数を断定していない。税/地域processing/extra tool/cache writes等は別。Fakeの実API費用0から推定していない。実adapterにはtoken・料金・timeoutの別上限が必要。

[Structured Outputs公式資料](https://developers.openai.com/api/docs/guides/structured-outputs)に対して、StarResult/Candidateはroot object、全field required、object追加属性禁止のschemaを確認。Pydantic/Zodの一致をローカルfixtureで検証した。実モデルのrefusal/incompleteや実際のschema受付は未検証。[WIF公式資料](https://developers.openai.com/api/docs/guides/workload-identity-federation)は読取りのみで、認証交換は実施していない。

## bootstrap BLOCKEDと配備判断

[停止報告](../../../../docs/P4_BOOTSTRAP_FORMAL_PLAN_STOPPED_20261010.md)では正式Plan後の入力/出力監査が停止し、Apply待ち条件に到達していない。[オフライン修復報告](../../../../docs/P4_BOOTSTRAP_AUDIT_RECOVERY_RESULT_20261010.md)はbool/stringおよびnull表現差の限定修復を確認したが、PR #5統合、exact mainへの承認、正式監査復旧/bindingの生成、実Apply controllerの別レビュー/承認は残る。旧Plan/journalを再実行・上書きしていない。

STARのオフラインPASSでこのBLOCKEDを解除しない。実AWSでのDynamoDB transaction/IAM/GSI/Streams/Lambda/SQS/Cognito/Recovery、物理TTL、30人性能/課金、CloudWatch発火と閉鎖読戻しは未実施。実STAR adapter/モデル/品質/prompt injection/token/WIFも未実施。今回の正式判定は「コード監査PASS、実AWS配備BLOCKED」。

## 次工程とdev検証・Closure

1. bootstrapの独立BLOCKEDを正規の監査復旧・承認経路で解決する。最新main/PR/Stateの確認と正式復旧は別作業の明示承認対象。
2. STAR監査commitをレビューし、GitHub書込み/main統合は別の明示指示に従う。現mainへの自動pull/rebase/mergeはしない。
3. Fake-onlyの配備候補を固定する。対象HEAD、CI、Linux Artifact SHA/version、Account/Region、backend/provider、資源全件差分、TTL、費用上限、State lineage/serial/VersionId、lock/State外資源、saved Plan SHAが具体化する前にApply承認を求めない。正式Plan、Artifact build/upload・Lambda配備も今回実行していない。
4. 配備と一時Enablementを別にレビューし、[承認テンプレート](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)/[runbook](P4_TERRAFORM_RUNBOOK.md)/最新AGENTSを使用する。今回の監査はEnablement承認ではない。
5. 将来の承認済み検証では、期限/transaction競合、同本人/複数本人、正式送信後save、配送種別、Worker/Recovery、JWT/CORS/Alarm、30人のpoll＋保存＋評価混在、固定Gate/費用を検証する。検証中のコード・memory・concurrency・provider変更でGateを合わせない。
6. Enablement承認には条件付き自動Closureも含める。Enablement成功とState/AWS正常ならSmoke/Performance PASS/FAIL・inbox確認にかかわらず証跡保存→Closure全件監査→1回apply→閉鎖読戻しまで同じ作業で完了する。
7. Closureは最新成功apply入力から4フラグだけfalseへ。create=0/replace=0、API/Worker/Streams/Schedulerの閉鎖4updateと今回validation Alarm削除だけ。Artifact/Lambda版/alias/Cognito/DDB/SQS/SNS/IAM/runtime/architecture/concurrency2/backend/provider維持、Account/Region/State/State外資源/lockを照合し、SHAをapply前に記録。逸脱/不整合/lockではapplyせず戻す。
8. Enablement/Closure partial failureは再apply/手修正せずread-only診断で停止。成功時はAPI disabled、両mapping Disabled、Scheduler DISABLED、validation Alarm0、lockなし、State外dev資源なしを読戻す。closedで分析を続け、再有効化/再負荷は新しい明示承認まで行わない。

AWS接続、State操作、正式remote Plan、Apply/Destroy、Artifact upload、Lambda配備、実OpenAI/有料リクエスト、GitHub書込みは今回すべて未実施。ソースとローカル証跡から通常closedの運用との整合を監査したが、現AWS閉鎖状態を今回読み戻したとは報告しない。
