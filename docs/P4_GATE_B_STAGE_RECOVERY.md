# Gate B Stage形式だけの復旧

2026-10-27 JST。診断003R2は33変更対象中32一致・1不一致。32一致には過去11件の再利用を含む。
今回確認した不一致はStageアクセスログ形式の`requestTimeEpoch`と`responseLatency`欠落のみ。
元RunのTerraform正常終了と失敗原因はUNKNOWNのまま、旧Planの再Applyは禁止する。

## 実行経路

標準`p4-standard-plan.yml`の新規承認descriptorに`stage_recovery`を明示する。
通常経路のbuildと新Lambda uploadは実行せず、State13に記録された既存Artifactの
bucket/key/VersionId/digestを固定再利用する。構成・依存・lock・runnerは新しいmainへ固定する。
旧診断source・State・Plan・消費済み承認を変更しない。IAMやTerraform構成の変更はない。

承認objectはState13のidentityとsnapshot canonical hash、既存Artifact、API/Stage、
観測済み4項目のbefore literalと期待6項目のafter literalを持つ。別の形式や対象を許可しない。
通常refresh付きPlanを1回生成し、全managed resourceのcoverage、actions、planned values、
drift、unknown、import/move/deposed/replace、outputsを照合する。
許可差分はStageの`access_log_settings[0].format`のみ、add0/change1/destroy0/replace0。
逸脱時は新Plan成果物をuploadせず停止する。

Stateとの照合では固定API資源のCORS集合の順序、および`allow_headers`/
`expose_headers`のASCII大小文字だけをProvider 6.65.0の集合定義に合わせて比較する。
AWS readbackでヘッダー名の小文字化を確認し、その値を使ったオフラインPlanでも
`no-op`とStateの表記不一致を再現した。許可集合・Originの大小文字・認証情報許可・
TTL・API閉鎖・他属性は変化を許可せず、重複を除去して差を隠すこともない。
この表記差だけのrefresh driftとApply後State読戻しにも同じ比較を適用する。
PlanのactionsはAPIで`no-op`、StageでFormatだけの`update`を維持する。
仕様根拠は採用版の[API resource schema](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/api.go)。

同じProviderのRoute refreshは、AWS応答で未設定の`authorization_scopes`（optional TypeSet）と
`request_models`（optional TypeMap）をnullから空集合/空mapへ変換する。
固定service moduleのadmin/business/preflight Routeに限り、この2属性のnull/空表現を
比較時だけ同一視する。AWSのJWT/Authorizer/接続先の一致を読取りで確認し、取得応答を返す
localhost模擬APIと実Providerによるrefresh付きPlanで、no-opと2属性の変換を再現した。
模擬API試験は実AWS refreshの成功とは区別する。非空scope/model、型違い、属性欠落、
認証・接続先・他属性の変更、unknown/replace等は拒否する。Stateの元bytes/hashは変更しない。
仕様根拠は採用版の[Route schema/flattenRoute](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/route.go)。

Stageの`deployment_id`はOptional+Computedで、auto-deployによる既存Deploymentをrefreshで取得する。
閉鎖APIの読取りでState13のキャッシュ値との差、既存DeploymentのAutoDeployed/DEPLOYED、
全28 Routeのidentity・JWT・Authorizer・接続先一致を確認した。これだけでは元Applyの正常終了は推定しない。
新descriptorでは必要時に`deployment_id_before`と`observed_deployment_id`を組で固定する。
元StateのID、auto_deploy=true、refresh driftの旧/観測ID、通常Planのbefore/afterが両方観測ID、
実行前後のGetStageと最終Stateが観測IDであることを照合する。他IDやDeployment変更操作は許可しない。
Stateの元bytes/hashは保持し、ApplyはFormat更新のみ。固定IDへのキャッシュ追従は別記して監査する。
旧descriptorは従来の完全一致を保持する。
仕様根拠は採用版の[Stage schema/read/update](https://github.com/hashicorp/terraform-provider-aws/blob/v6.65.0/internal/service/apigatewayv2/stage.go)。

新Planは既存のprivate S3経路で5個の成果物を新規保存し、固定VersionIdとbytesを読む。
envelopeは最後に保存する。公開Actions artifactは既存recipientへのCMS暗号文と固定summaryのみ。
State本体を書き換える操作はPlan承認に含めず、通常のS3 lock取得・解放だけを含める。
`-refresh=false`、`-refresh-only`、target指定、force-unlock、再Planでの回避を行わない。

Applyはその新saved Plan hash/source/runに対する別の明示承認を要求する。
既存標準Applyのmain/actor/Environment/期限/Plan検証を保持し、immutable envelopeと
Plan bindingのrecovery object・既存Artifact・State identityも一致させる。
以前のApply成功を推定したreceiptや承認は作成しない。

## 安全確認と上限

実行前後に固定State/lockとAWS4入口閉鎖、Stageのbefore/afterを読み戻す。
標準Workflow実行中はそのEnvironmentだけreadiness2項目がtrueで、他方2項目はfalse。
operatorは終端確認後に実行Environmentをfalseへ復帰し、両Environment全4項目のfalseを読む。
readinessの一時変更・Secret更新・dispatch・復帰は、対象固定の新しい操作承認に含める。
AWS4入口を有効化する承認ではない。

Plan側のPython orchestrationはSDK512・物理HTTP512を別々に数え、SDK内の再送を拒否する。
**Terraform Go backend/providerの通信はこのcounterの対象外**であり、全AWS HTTPのhard capとは呼ばない。
Terraformは既存roleの権限・retry0・parallelism2・Plan20分・job55分・session期限で制限される。
operatorのGitHub要求とcached SSO readbackには別の回数上限を承認パッケージで固定する。
推定費用・操作上限はAWS請求の強制停止を保証しない。

State/lock/Account/Region/source/入力/hashの不一致、想定外の入口有効化、readiness逸脱、
未知・認証・権限・通信エラー、証跡保存失敗、期限超過は停止する。
PlanやApplyの途中失敗・UNKNOWNは再実行・手動unlock・State修復・rollbackで回避しない。

## 現在の位置付け

このコード・Mock/CI検証はAWS実行承認や復旧成功を意味しない。
正常Apply終了・Stage反映・State一致・入口閉鎖・readiness falseの実証拠が揃って初めて復旧成功とする。
OTP、実Bedrock/OpenAI、性能試験、Enablement、hosting配備、外部公開は別承認。
正式Terraform1.14.9/Provider6.65.0、PR43 Draft/HOLD・Issue50 OPENを維持する。

公式仕様: [通常Plan](https://developer.hashicorp.com/terraform/cli/commands/plan)、
[Terraform1.14 S3 lock](https://developer.hashicorp.com/terraform/language/v1.14.x/backend/s3)。
