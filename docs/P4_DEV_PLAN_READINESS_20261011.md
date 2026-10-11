# 正式dev Plan再開の安全条件と次工程

2026-10-11。Bootstrapの成功済みApplyとPR #5〜#9統合を保全し、実AWSへ接続せずに準備する。
本書はPlan、Apply、S3書込み、Enablement、STAR配備、OpenAI呼出しの承認ではない。
実行対象main・runtime・lock・Artifact・State identity・期限・費用は別のprivate candidateへ固定する。

## 今回の根本原因修正

旧builderはconsole scriptの`bin/`をZIPから除外する一方、dependencyの`.dist-info/RECORD`には
そのscriptのshebang由来hashを残していた。Pythonのインストールパスが違う独立stageでZIP hashが変わり、
ローカル承認hashとGitHub hosted runnerのfresh buildが一致しない。
builderはZIPに収録するRECORD行だけを保持し、順序を固定する。runtime本体・依存version・license・
METADATA・既存内容検査は維持する。入力stage/旧ZIPを書き換えず、新ZIPにだけ反映する。
malformed列、収録行の重複、RECORD自身の不正・欠落を拒否する。
根拠は[PyPA installed RECORD仕様](https://packaging.python.org/en/latest/specifications/recording-installed-packages/)。

Planのworkflow再実行はAttempt1以外をGit/SDK/build/Terraformの前で拒否する。
別RunIdを1回だけdispatchするsingle-operator運用・journal・実行Gateの閉鎖は別途必須であり、
このAttempt検査だけで別runの多重起動を防止したとは扱わない。Applyの既存journal/retry契約を変更しない。
CI Planのtransportは新Artifact1件とsidecar5件の合計6Putを維持し、envelopeを最後に保存する。

## 実Plan前のGate

1. 最新main/CIとsource tree、Python3.14/Linux x86_64、Terraform1.14.9、provider4 lockを固定する。
2. locked wheelをfresh stageへ展開し、独立インストール/別PythonパスのZIP hash一致、内容/秘密情報検査、
   展開後4 handler/native extension/Fake実行を確認する。旧Artifactを上書きしない。
3. Account/Region、operator/CI Role/OIDC、Bootstrap Stateとdev Stateのlineage/serial/VersionId/hashを区別する。
   保存されたdev61資源は歴史的観測であり、将来のplanned baseline件数を61へ固定しない。
4. 有効な別承認の後だけlive State/closed/lock/実体/State外資源、effective権限とexact version GETを照合する。
   drift・不整合・他operator・active lockがあれば開始しない。
5. GitHub dev環境のbranch保護、対象4変数の現在値、正常/異常のGate=false戻しと読み戻し能力を確保する。
   非空不一致やGate=trueを無断で上書きしない。GET成功と管理書込み成功を区別する。
6. 一意RunId/Attempt1、Plan最大1回、exact6Put、通常dev lockのみを明示承認する。
   canonical State/IAM書込み・force-unlock・再Plan・別run retry・Applyは含めない。
7. 後検査・lock不在・GitHub Gate=false・private証跡保存まで同じ承認に含める。
   partial/timeout/結果不明・閉鎖失敗は保全して停止し、成功へ読み替えない。

## 費用と保持

最新の[AWS公開料金表](https://aws.amazon.com/s3/pricing/)を未認証で保存・地域別に照合する。
request数・転送bytes・保存期間を別にモデル化し、無料枠/共有残量を未確認のまま相殺しない。
S3の同一usage名でもMRAPと通常transferを混同せず、Tokyo outboundはAWSDataTransfer側の該当SKUも確認する。
費用提案は実請求の強制停止保証ではない。新saved Plan/sidecarは保存継続費用が残る。
[S3 backend公式](https://developer.hashicorp.com/terraform/language/backend/s3)のState/lock権限を分ける。

## Plan以降の準備順序

|工程|オフラインで完了するもの|別承認後の実機確認|
|---|---|---|
|正式dev Plan監査|全address/action/drift/deferred/import/move/unknown/output監査、retention/boundary/runtime確認|fresh saved Plan・SHA、前後State/lock|
|安全検証・Closure|最新成功入力から4フラグだけ戻す手順、baseline集合＋承認Alarm差分|Enablementと条件付き自動Closureを同時承認、閉鎖読み戻し|
|STAR Ver.1.4 / Coaching V1/V2|固定prompt/30点/深掘り/V1/本人分離/冪等性/RecoveryのFake・契約テスト|新Artifact/Planに固定したAWS配備・限定Smoke|
|Frontend実API・Cognito|Bearer、EMAIL_OTP、401更新、POST固定キー、本人別RecoveryのMock/契約/E2E|実user pool/client/JWT claims、EMAIL_OTP inbox、CORS/API実接続|
|OpenAI Provider|既存transport/schema/deadline/quota/retry禁止のmock検証、WIF準備|別の本人・Role・model・回数/token/費用承認、実モデル品質|
|30人性能・費用|既存MaxConcurrency=2、capacity/throttle/SDK roundtrip/usageモデル|正式p95 Gateと実AI負荷を別承認で測定|

通常API p95 2秒の目標を後付け変更しない。Fake、offline、cached warmの結果をlive性能/採点品質へ流用しない。
Coaching V2/V1、STAR Ver.1.4、既存Session/Attempt/Evaluation、State・Git・journal・ledgerを保持する。
