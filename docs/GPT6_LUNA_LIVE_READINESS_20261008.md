# GPT-6 Luna 実接続準備・次工程の承認資料（2026-10-08）

正式状態は `GPT6_LUNA_PROVIDER_OFFLINE_VALIDATED_PENDING_LIVE_APPROVAL`。
本書は実接続・upload・applyの承認ではない。既存Formal Performance Gate FAIL/reviewは維持する。

## 再確認した基準

- Windows / repository root: `C:\Users\user\Documents\ai_interview_mvp_design`。
- 開始時main/HEAD/remote main: `8d23293476f56a813c8efb8ea849d8e70afab490`。
- 開始時の変更文書1件・未追跡文書5件は保持し、今回のcommit対象から除外する。
- 2026-10-08 20:33 JSTのAWS読取り: serial12、61資源、以前と同一lineage/State SHA/VersionId。
  API disabled、Worker/Streams Disabled、Scheduler DISABLED、validation Alarm0、lockなし。
  dev名前空間のLambda/mapping/DDB/SQS/API/Scheduler/IAM/log-groupはStateと一致。
  名前空間監査の範囲を超える全AWS資源の不在を証明したとは扱わない。
- Lambda API/Worker/Dispatcher version3、Admin version1、5alias一致。現配備はFake設定。
- 開始HEADのBackend/P4 offline/Frontend CIはremoteから再確認し全success。
- 新証跡: `backend/.p4-artifacts/gpt6-luna-live-readiness-20261008-02/`。
  Account/lineage/binding/role/boundary原文はprivate JSONに保存し、Gitへ含めない。

## Artifact判断

候補 `backend/.p4-artifacts/gpt6-luna-candidate-20261008-02/app.zip` を再利用する。
source=`308148891b39423127688df60bc9fe8d72716288`、size=19,093,023 bytes、
SHA-256=`2982d8d049f17543aa25ab01ec8376bcc1bdf21c557d78a977ab2dec5d1d81aa`。
provenanceの38ファイルを実bytesで照合済み。source→開始HEADのsrc/pyproject/lock/builder差分0。
今回の変更もskills/tests/docsだけで配備bytes不変。既存Linux/native ABI/mock smoke証跡を再利用し再buildしない。
新正式S3 key/VersionId・saved planはまだ存在せず、旧Artifactは保持する。

## WIFの確定事項と設定案

2026-10-08 20:36 JSTの `GetOutboundWebIdentityFederationInfo` はHTTP404 `FeatureDisabled`。
これはこの読取りで未有効が確認された結果で、AccessDeniedやSDK未対応と区別する。
issuerは取得不能のため推測しない。Workerの既存business policyとboundary v1も読取り保存済み。

[AWS開始手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_outbound_getting_started.html)に従い、
別承認の管理者操作でアカウントのoutbound federationを有効化する。管理者だけに
`iam:EnableOutboundWebIdentityFederation`、確認者に`iam:GetOutboundWebIdentityFederationInfo`を用意する。
これらをWorkerへ付与しない。SCP/session policy/必要なendpoint policyの明示Denyも別途確認する。

Worker business policyへ追加する案は次の1statementだけ。既存statementは保持する。

```json
{
  "Sid": "WorkerOpenAIWIF",
  "Effect": "Allow",
  "Action": ["sts:GetWebIdentityToken"],
  "Resource": ["*"],
  "Condition": {
    "ForAllValues:StringEquals": {"sts:IdentityTokenAudience": ["https://api.openai.com/v1"]},
    "NumericLessThanEquals": {"sts:DurationSeconds": 300},
    "StringEquals": {"sts:SigningAlgorithm": "ES384"},
    "Null": {"sts:IdentityTokenAudience": "false", "sts:DurationSeconds": "false", "sts:SigningAlgorithm": "false"}
  }
}
```

[AWS条件キー](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_outbound_policies.html)に合わせる。
Resource `*` はtoken vendingに必要で、対象principalは付与先Worker roleだけに限定。
共有boundaryへの追加は同条件に **ArnEquals/aws:PrincipalArn=実Worker role ARN** を加える。
他roleへの許可拡張を避ける。`sts:TagGetWebIdentityToken`/AssumeRole/追加信頼policyは不要で提案しない。
privateの `worker-policy-proposal.private.json` / `boundary-proposal.private.json` は現policy全文へ
このstatementのみを追加したレビュー用具体物。実変更なし。boundary更新時はbootstrap_contractおよび
boundary監査期待値の整合変更と否定simulationを同じ別承認の実装で行う。

Terraform差分案は `terraform/modules/service/iam.tf` のworker_statementsへ明示WIF opt-in条件で上記を追加し、
既定false、他3role不変とする。worker_ai_environmentのauth方式と一致しなければ拒否する。
新resource/依存追加なし。shared boundaryは既存bootstrap管理経路の別変更として扱い、Terraformへ二重管理導入しない。
本工程では実Terraform設定を変更せず、差分案を作成した。

[OpenAI AWS WIF設定](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws)では、
有効化後に実issuerを記録し、regional `https://sts.ap-northeast-1.amazonaws.com`、audience上記、TTL300、ES384で照合する。
初回tokenは別承認後にメモリ内でclaimsのみ確認し、issuer/audienceと **sub=private証跡のWorker IAM role ARN完全一致**
を確認する。STS assumed-role session ARNを推測でmappingへ入れない。
OpenAI providerはOIDC discovery/JWKS、専用project service account mapping、scope `api.model.request`。
project/provider/service-account ID、gpt-6-luna利用権限とrate/spend制御は管理者の確認が必要。
現時点は未登録・未確認。SigV4や一時Access Keyをsubject tokenに代用しない。

ローカルEvalのAWS SSO実行者はWorkerと別principalで、Worker mappingを流用できない。
別の狭いEval role/grant/boundaryと正確なsubject mappingを別承認するか、明示Secret方式を選ぶ。
WIF不可時のSecret案は同Account/東京の既存専用Secret ARNのJSON `api_key`、Workerだけの
`secretsmanager:GetSecretValue`＋boundary同ARN許可、CMK利用時のみ同keyの限定`kms:Decrypt`。
Secret作成/値登録は本人の安全な操作で別承認。平文Terraform入力・キーのチャット転記・無断fallbackは行わない。

## 実機接続コードと残るbinding

`backend/skills/p4/coaching_binding.py` は既存suiteを接続するライブラリ。
`execute_bound(raw, digest, manifest_raw, journal, ..., audit, authenticate, close)` が承認JSON SHA、
active manifest SHA/Account/東京/dev/4flag、明示provider、3主体、Admin scope、
3callbackのsourceファイルSHAと実関数source pathを確認する。
実行は成功Enablement receiptと最新Stateの監査callbackがTrueを返す場合だけ。
partial apply/不整合/lock/State外資源はauditで停止し、auth・取引・Closureを開始しない。

開始journalはprivateの未使用pathを排他的作成/fsync。auth失敗を含むsuite内失敗でもClosureへ進み、
読戻し条件が揃うまで成功にしない。既存auth_e2e.login＋Cognito GetUserの`sub`で3主体を照合する
`authenticate_existing`を追加した。token/refresh tokenは永続化せず、終了時API token参照を消去する。
refresh/logout/実expiry検証は別の既存auth_e2e経路のままで、今回のsuite実行結果へ合算しない。

承認JSONの必須キー: `live_authorized`, `conditional_closure_authorized`, `enablement_succeeded`,
`run_id`, `account_id`, `region`, `manifest_sha256`, `subjects` (USER_A/USER_B/ADMIN),
`provider`, `expected_rounds` (0/3), `admin_writes`, `callback_sha256` (audit/authenticate/close)。
openaiは`paid_calls_authorized=true`、Admin書込みは`exclusive_test_window_verified=true`も必要。
これらのtrue値は実承認/成功receiptからのみ生成し、準備中に実行可能な承認JSONを作らない。

**残る実binding**: 新配備後のmanifest、Enablement成功receipt、専用usersのsub、承認時間、
限定provider/calls条件、3つのレビュー済みcallback source SHAを確定する必要がある。
auditは最新State/manifest/providerと実専用user windowを検査、authenticateはhidden emailで上記helperへ接続、
closeはP4 runbookに従うplan全件監査・1回apply・読戻しを実装する。
現時点は新plan未作成のため実Closure adapterは未接続。任意shell hookは使わない。
実要求0のoffline成功を実行器全体や実IAMの成功と扱わない。

`cleanup_candidates` はjournalに実記録されたSession/Attempt/Evaluation IDからcodec.keyで
正確なnative keyを作り、承認済みread_exact(GetItem)で存在・PK/SK一致を確認して一覧化するだけ。
削除、Scan、Query、USER全消去は含まない。Dispatch/CoachingTurn/Idempotency/Admin変更記録等は
追加の実キーinventory・関連関係/terminal status/第三者更新確認後に別承認する。未知キーは残存として報告する。
ProviderUsage利用予約は返却・削除せず保持する。cleanupを「完備した削除機能」とは扱わない。

## 限定有料Eval案

固定corpus19件×low/medium各1回=最大38 Responses要求、合成fixtureだけ。利用者答案は送らない。
max_output_tokens4096、timeout40秒、再送なし、OUTCOME_UNKNOWNも1要求として数え追加実行しない。
専用project、Standard/short context、cache hitなしで料金を見積もる。
[料金](https://developers.openai.com/api/docs/pricing): 入力$0.10/出力$0.50 per 1M tokens。
入力6000 tokens/要求という仮定なら38件で$0.100624。これは入力の強制上限でも実測でもない。
承認提案額はAPI部分 **USD1.00**、事前に全promptの実token数・tierを確認し保守的上限を算定する。
現Eval runnerは件数gateを持つがドル上限の強制gateを持たないため、USD1をhard capとして実行しない。
hard capが必要ならtoken-count上限＋開始前の最悪額予約・usage不明停止を実装し別途offline検証する。
税/為替/地域処理/cache writes premium/AWS費用は別。OpenAI project budgetを強制停止と誤認しない。
月100/全体3000の予約は全支出上限ではない。reference labelsは提案、manual annotation未評価はnull。

[モデル](https://developers.openai.com/api/docs/models/gpt-6-luna)、[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)、
[reasoning](https://developers.openai.com/api/docs/guides/reasoning)、[token exchange](https://developers.openai.com/api/reference/workload-identity-federation)を再読取りした。
既存model固定/strict schema/reasoning standard/low-medium/store=false/background=false/tools=[]を維持。
[データ管理](https://developers.openai.com/api/docs/guides/your-data)のとおりstore=falseを全保持ゼロと説明しない。

## 次工程で承認を分ける具体物

1. WIF管理者有効化＋Worker policy/boundary proposal、OpenAI専用mapping。issuer/token初回確認も範囲に含める。
   Secretを選ぶ場合はこのWIF案を実行せず、Secret ARN/限定policy/登録主体を別固定する。
2. 上記候補ZIPの新keyへの1回upload。正式VersionId/checksum/binding確定後、閉鎖維持のfull saved planを作成する。
   4Lambda/5alias更新は予想にとどめ、全差分・Account/State・plan SHAをレビューして別apply承認する。
   実行済みSHA `2ea70506a410a1c98c4036bcc8f9ec4bb0b4c15dd2946bf56a49ad0ef504afcb` は再apply禁止。
3. 38件の有料Eval: 認証主体、corpus SHA、max_calls38、effort、token/予算条件、未使用journalと承認SHAを固定する。
4. Fake通常/three/provider_failureまたはOpenAIを個別構成として固定したEnablement。
   最新Stateから保存したplanの全件監査とSHA、test users/window、取引・障害注入の有無を個別承認する。
   通常Fake/three/failureは同じ配備設定で一括実行できると扱わない。
5. Enablement承認には[既存テンプレート](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)の条件付き自動Closureを同時に含める。
   最新成功apply入力から4flagだけfalse、最新Artifact/version/alias/provider設定保持。
   create/replace0、4閉鎖updateと承認済みvalidation Alarm削除だけ、他baseline no-op。
   Closure SHAはapply前に記録し条件成立なら追加承認なし1回apply。逸脱/lock/不整合/partialはread-only停止。
6. Cleanupは実取引journalから得たexact-key一覧・更新条件を後で別承認し、未実行一覧を残す。

今回のAWS変更/IAM変更/upload/apply/Enablement/token発行/Secret登録/有料AI要求はすべて0。
IAM simulation ConditionCheck1とWorker/Dispatcher/Recovery実取引は未確認のまま区別する。

## 今回のオフライン検証

Ruff check/format成功。Backendは1102 passed/57 deselected。最終gate修正後の接続・既存suite関連は
24 passed（追加11件）。承認不一致/主体重複/callback改変/未承認課金/非排他的Admin/manifest差分拒否、
認証失敗後のClosure、journal再実行拒否、不安全State停止、限定key照合を検証した。
AWS実機成功や採点品質のPASSは付けない。Terraform/Frontend配備入力に変更はなく、最新commitのCIで確認する。
