# GPT-6 Luna — WIF・配備の2段階承認

正式状態は `GPT6_LUNA_PROVIDER_OFFLINE_VALIDATED_PENDING_LIVE_APPROVAL`。
本書は操作承認ではない。既存の未commit文書5件と変更文書1件を保全する。
前回結果は [実接続準備](GPT6_LUNA_LIVE_READINESS_20261008.md)、
今回の実値・差分全文・SHAは `backend/.p4-artifacts/gpt6-luna-stage-approval-20261008-01/` のprivate資料に置く。

## 最新の実値とWIF前提

今回の読取りでもdev Stateはserial12／61資源、同一lineage/VersionId/SHA、4フラグfalse、
API disabled、両mapping Disabled、Scheduler DISABLED、Alarm0、lockなし。
WIFはHTTP404 `FeatureDisabled`。Worker policy/boundary原文、実Worker role ARN、
ローカル実行者の実IAM role ARNを再取得した。issuerは未取得で、仮値を確定していない。

[AWS開始手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_outbound_getting_started.html):
管理者に `iam:EnableOutboundWebIdentityFederation`、確認者に `iam:GetOutboundWebIdentityFederationInfo`。
IAMはAccount全体の設定であり、東京のLambda1個だけを有効にする操作ではない。
有効化すると既にSTS token vendingを許可されている他principalも、各identity policy/boundary/session policy/SCP等が
許す限りJWTを発行可能になる。今回の新runtime grantはWorkerだけだが、Account全体の既存管理者権限を消去しない。
OpenAIは専用Projectと完全一致subject mappingで別途制限する。明示DenyはAllow/boundary追加で解除できない。

新grantは `worker_wif_enabled=false` が既定。service moduleはdev Workerのbusiness policyに
`sts:GetWebIdentityToken`、Resource `*`、audience `https://api.openai.com/v1` のみ、
TTL<=300秒、ES384、欠落conditionキー拒否を追加する。
共有boundaryはbootstrapだけで管理し、同条件＋ `aws:PrincipalArn=実dev Worker role ARN` を追加する。
API/Admin/Dispatcher/test Workerへ追加しない。Secret選択時はWIF grantを同時保持しない。
既存61資源のresource block追加・削除0。既定入力のIAM差分0。runtime/architecture/512MB/
Worker60秒/MaximumConcurrency2/backend/provider lockは維持する。

提案identity＋boundaryのAWS `SimulateCustomPolicy` は8ケースPASS:
Worker Allow、別/混在audience、TTL301、RS256、別API principal、audience欠落のDeny、明示Deny。
これは未apply提案の計算で、実STS token vendingや実DDB取引の成功ではない。
既知のtransaction ConditionCheck1の未確認状態は維持する。

## OpenAI設定順序と未結合値

[公式WIF手順](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws)に従う。

1. 承認後にAWSのfeatureを1回有効化し、`IssuerIdentifier`/`JwtVendingEnabled`を読み戻す。
2. 実issuerのOIDC discovery/JWKSとissuer一致を確認する。未取得・不一致・未知hostで停止する。
3. 専用Project名案 `ai-interview-dev-luna-validation`、Worker Service Account名案 `worker-luna-validation`。
4. Workload Identity Providerを先に登録し、実issuer＋audienceを設定。uploaded JWKSへ無断切替しない。
5. Worker mappingを完全一致 `sub=実Worker IAM role ARN`、専用Project/SA、scope `api.model.request` へ限定。
   このsubjectは現role ARNに基づく設定案で、実JWT照合済みとは扱わない。
6. projectのgpt-6-luna利用権限・rate/spend制御を確認する。Project budgetを強制停止と誤認しない。
7. Workerの直接invoke Smokeで実JWT claimsとmappingを照合する。不一致なら有料要求へ進まない。

組織/Project/Service Account/Identity Provider/Mapping ID、issuer、model access読戻しは未結合。
これらは管理者のOpenAI画面または承認済み管理APIの読戻しで確定する。APIキー/tokenをチャットへ転記しない。
今回の接続環境にOpenAI管理credentialはなく、登録を行っていない。

ローカルEvalは別principalで、Worker mappingを流用しない。実ローカルIAM role ARNは
`local-eval-identity.private.json` に保存した。追加AWS grantは提案しない。
利用する場合は **この既存roleに対する別のOpenAI Eval SA/mapping** を明示承認し、実JWT subjectも照合する。
既存roleが管理者roleの場合、そのroleを使える他管理者にもmappingが有効になることを承認範囲へ含める。
それを許容しない場合は、既存の専用Eval principalを本人が指定する必要がある。新roleは本案に含めない。
AWS側Denyでtokenを発行できない場合は停止し、IAMの追加拡張やSecret fallbackを行わない。

## Worker WIF SmokeとArtifact変更

既存ZIPには、実WorkerのJWTを照合してtoken exchangeだけを行う入口がない。
そのため `wif_smoke.py` とWorker内の直接invoke経路を追加した。新HTTP/API routeは0。
Fake＋validation-only＋専用flag/run_id＋issuer/Provider/SA IDの明示設定が必要。
通常のSQS処理とAPI回答からこのoperationを選べない。
Worker `live` aliasのAWS InvokeFunction権限を持つ承認済み実行者だけが呼び出す。
SDK1attempt、TTL300/ES384、同一40秒deadline。JWT/access tokenはメモリだけ。
issuer/audience/正確なWorker sub/TTLを検査し、OpenAI exchangeが署名/mappingを検証した後だけ成功する。
Responses/DDB/SQSへの要求0。返すのは安全なclaims項目と成功状態で、credentialは含めない。
運用tool `wif_smoke_live.py` は承認SHA、manifest、mapping値、排他的invoke journalを確認する。
未知の送信結果を再invokeしない。閉鎖状態でも直接invokeでき、API/mapping Enablementは不要。

**配備入力は変更あり**。旧候補source `308148891b39423127688df60bc9fe8d72716288` /
SHA `2982d8d049f17543aa25ab01ec8376bcc1bdf21c557d78a977ab2dec5d1d81aa` は保全するが、
新Smokeには使用しない。新候補を固定commitから作成し、source/size/SHA、一意S3 keyをprivate Stage1対象へ確定する。
依存/SDK/builderは変更しない。新候補以外のupload・旧key上書きは承認しない。

## USD1・38要求のEval gate

`provider_eval.py` は最大38生成要求（19合成fixture×low/medium）。追加で最大38のtoken-count preflightを
明示承認し、[公式count endpoint](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count)に
実際のmessages＋JSON schemaを送る。計測前には生成要求を送らない。現工程の実token計測は未実行。
実payload群のSHA、認証読戻しSHA、Project/SA/issuer/subject/モデル権限を承認へ結合する。

2026-10-08の[公式モデル料金](https://developers.openai.com/api/docs/models/gpt-6-luna)を基準に、
Fast×long context×regional uplift、cache-writeの最大単価も保守的に含める。
入力550 nano-USD/token、出力1650 nano-USD/token、出力上限4096（reasoningを内包）。
実測入力countから全要求の上限額を計算し、**USD1を超えれば生成を拒否**する。
入力6000という仮定なら38件の予約額USD0.3822192。これは実測額ではない。
料金snapshot SHAと当日UTCの `pricing_verified_on` を承認する。当日の公式料金確認がない場合、
またはsnapshot期限2026-10-15を超えた場合は停止する。料金が変わればsnapshotと予約を再計算する。

全件分を最初に予約、各要求開始前にfsync journal、応答後にusageによる保守的使用済み額へ振替する。
使用済み＋予約済みで管理し、unknown usageは予約を保持して残りを停止。
予約を超えるusage、payload変更、call上限、予算見込み超過でも追加要求を拒否する。
同じ承認SHAのledgerは結果pathを変えても再使用できない。
USD1はこのrunnerの追加生成要求を抑止する条件で、請求額の完全保証ではない。
税/為替/AWS/S3/Lambda/Alarm費用は別。quota100/3000とProject soft budgetも支出保証ではない。
通常のOpenAI業務suiteは本38件に含めず、今回の第2承認案ではFake業務suiteだけを対象とする。

## Closureの実行経路とEnablement gate

`closure_adapter.py`＋`closure_aws.py` は実Terraform commandを固定したadapterで、任意shell hookを受け付けない。
承認SHA、engine/driver source SHA、Enablement saved plan SHA、成功receipt、Account/Region、
State lineage/serial/VersionId/SHA、最新input/manifest/Artifact/provider/version/aliasを結合する。
receiptは実apply-started/completed記録とAWS読戻しから `save_enablement_receipt` が生成する。
準備中に成功receiptは作らない。未取得pathは実行時の必須パラメータで、欠落すると拒否する。

planは最新成功入力から4フラグだけfalseへ変更。全State instanceを監査し、61 baseline＋承認Alarmのみ。
create/replace0、正しい方向の4閉鎖update、承認されたAlarm住所と名前の削除、他baseline no-op。
refresh drift/unknown/deferred変更、outputのArtifact/provider/version/alias変更も拒否する。
plan SHAを記録し、直前に再hashとState/lock/名前空間再確認を行う。
排他的attempt記録後に1回apply。partial/失敗後は再plan/apply・手修復をせずread-only診断へ移る。
閉鎖readbackは最大60秒の読取り待機。API・両mapping・Scheduler・Alarm0・lock・State外資源なし、
最終61資源、最新Artifact等の保持を確認してjournalへ保存する。
実閉鎖証拠が揃わなければ成功にせず、active残存可能性を明示する。

`closure_readiness.py` のoffline実行証明＋現在のsource SHAが一致するまで、
`terraform_dev`の有効化applyと `coaching_binding` の実機suiteを拒否する。
最新成功receipt/manifest/Enablement planは未存在のため未結合で、今はEnablement不可。
[条件付きClosure承認テンプレート](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)と
[Terraform runbook](P4_TERRAFORM_RUNBOOK.md)をそのまま用いる。
AWS Account全体のWIFやIAM grantをClosureでrollbackせず、4フラグ閉鎖と承認Alarm削除だけを行う。
既存Formal Performance Gate FAIL/reviewは変更しない。

## Suiteとcleanupの範囲

| 構成 | Worker設定 | 専用Enablement・window | 検証 |
|---|---|---|---|
| Fake normal | fake。必要時WIF Smoke flagは別の直接invokeだけ | 4フラグ・承認users | owner/session分離、初回completed、再送、retry_attempt、履歴、Admin読取 |
| Fake three | coaching_three＋validation-only＋USER_A hash完全一致 | 別manifest/plan/Enablement | 3深掘り、completed、stale/再送/履歴 |
| Fake failure | provider_failure＋同allowlist | 別manifest/plan/Enablement | failed、retry_evaluation、同失敗構成のretry terminal |
| Admin writes | 上記Fakeの承認構成 | 全enabled usersが専用3主体だけ、承認開始/終了時刻 | CRUD/並替/版競合/復元。第三者更新を上書きしない |
| Runtime観測 | exact function/aliasのCloudWatch metrics読取り | 排他的検証window | Worker/Streams/Recovery invocation。取引成功の証明とは区別 |

`SuiteAudit`が実receipt/current manifestとStateを照合。`CognitoAuthenticate`は既存EMAIL_OTP＋GetUserの実subを確認。
Admin直前に再監査する。refresh/logout/実expiryは既存auth_e2eの別経路を維持する。
成功Fake Evaluationは通常業務経路の観測になるが、IAM ConditionCheck全ケースの成功へ読み替えない。
ConditionCheck1、Recoveryのreclaim/lease境界等は、専用データの実keyと承認された障害/取引手順・receiptがまだ必要。
`runtime_receipts.py`をSuiteAuditへ接続し、run-owned Evaluation/Dispatch/Admin冪等recordと
3つのRecoveryCursor revisionをexact GetItemで読む。Worker/Dispatcherのterminal/delivery記録、
Admin ConditionCheckを含む業務record、Recovery checkpointの更新を観測する。
未観測はnot_run。これは実取引記録の観測で、reclaim/ACK loss/lease境界や独立ConditionCheck1は未実施として分ける。
`observe_runtime`も未実施ケースをnot_runに保ち、Scheduler invocationだけでRecovery実取引PASSにしない。
異なるProvider構成を1つのEnablementで検証済みとは扱わない。

`cleanup_exact.py`は承認SHA、実closed-readback SHA、Account、run journalに含まれるexact key、
item全文hash/revを確認し、rev/data条件付きDeleteItemを行うadapter。SDK1attempt、ack不明時再削除なし。
Scan/Query/partition全消去は0。ProviderUsage、共有bank、未知の補助recordは対象外。
実作成ID・snapshotは未存在なので削除対象は今は空で、cleanup実行不可。残存は別一覧で保存する。

## 2段階の承認対象

第1承認はprivate `stage1-targets.private.json` のexact Account/role/boundary/候補ZIP SHA/一意keyを対象とする。
AWS feature有効化1回、issuer読戻し、専用Project/SA/provider/mapping登録の範囲、ZIP新key upload1回を承認する。
Worker/共有boundaryの変更範囲は上記限定statementだけで、正式saved plan作成へ進む。
**TerraformのIAM変更とrolloutのapplyは、SHAが確定する第2承認まで行わない。**
bootstrapとdevの別Stateを混ぜず、共有boundaryはbootstrapのfull saved planで管理する。
issuer等が初めて得られる部分は未結合のまま承認し、実値が許可条件と一致したときだけ設定を確定する。
OpenAIの新IDは本人/管理者操作後の読戻しが必要で、credentialのチャット共有を求めない。

第2承認には、固定bootstrap/dev rollout plan SHA、S3 VersionId/checksum、最新State基準、
Worker WIF Smokeの具体設定/InvokeFunction主体、別Eval principal mapping読戻し、料金/requests SHA、
最大38生成＋38count/USD1 ledger、専用USER_A/B/ADMIN、排他的windowを含める。
Fake各構成の固定saved planと一時Enablementには条件付き自動Closureを必ず同時承認する。
将来Stateに依存する次構成planのSHAは推測せず、確定planを使う。別構成の未承認applyを追加しない。
cleanupは実取引後に得たexact-key snapshotだけを承認対象にする。

現工程のfeature有効化/token発行/credential登録/IAM変更/OpenAI mapping作成/upload/apply/
Enablement/有料要求/実データ削除はすべて未実施。
