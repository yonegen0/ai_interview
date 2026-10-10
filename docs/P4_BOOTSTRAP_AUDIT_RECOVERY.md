# Bootstrap saved Planの監査復旧

2026-10-10の正式PlanはTerraform自体が成功したが、後続監査で停止した。本経路は、そのsaved Planを再生成せずに監査を復旧するための独立実装である。コードレビュー・CI・mergeは正式復旧やApplyの承認を意味しない。

## 原因と根拠

| 論点 | 実ログ・private証跡の事実 | コードからの判定 |
| --- | --- | --- |
| A: Boolean | `show.stdout.private.log`の`variables.worker_wif_enabled.value`は文字列`"false"`。入力JSONはboolean `false` | `execution_environment`がTF_VARへ文字列を渡し、旧`audit_plan`はJSON型を含む入力全件一致を要求していた |
| B: SES null | State outputsで`ses_domain_verification`は省略。planned outputsではknown null、型dynamic | 旧outputs比較はkey集合まで完全一致であり、A解消後にはここでも停止する |
| C: output_changes | 各出力直下に`actions`, `before`, `after`, `after_unknown`, sensitive maskがある。SESはno-op/null/null/false | 構造理解は既存コードと一致。新監査は必須key・出力集合・値を個別照合し、単にbefore==afterだけの判定を強化する |
| D: 後続条件 | 完全な実show JSONを純粋な修正監査に入力すると32資源を通過 | 入力/SES例外以外を削除していない。正式復旧時には現AWS/State/主体/全hashを再照合するため、オフラインPASSは正式成功の保証ではない |
| E: revision | 元Plan sourceは`bc0919e13477f4d86609e1c7ed51590e118a8fd2` | 新しい監査revisionは別の承認値。元descriptorのsource_shaを変更しない |

元の失敗記録は`READ_ONLY_DIAGNOSIS_REQUIRED`、CLI stderrは固定`BOOTSTRAP_MAINTENANCE_STOPPED`で、元コードは例外詳細を公開していない。`MaintenancePlanInputs`という停止条件は、保全した同じshow JSONと入力を旧監査コードへオフラインで渡して再現した結果であり、元ログにその文字列が記録されたとは主張しない。

Plan SHAは `e2510fe49cabfabc7dae289caa3d13cead3f65101341699f0372f7614b2f6450`。実資源差分はcreate=0/update=2/replace=0/destroy=0、その他30資源no-op。元State/version inventory不変・lock解放・binding未生成の停止記録を保持する。private Plan、State、Role ARN、OIDC subject/emailは公開fixtureへコピーしない。

Terraformの[JSON形式仕様](https://developer.hashicorp.com/terraform/internals/json-format)と[1.14.9のJSON生成コード](https://github.com/hashicorp/terraform/blob/v1.14.9/internal/command/jsonplan/plan.go)を参照した。サニタイズfixtureは実1.14.9の構造（format_version=1.2、SES dynamic null、flat output_changes）を転記し、値と32資源は合成データを使用する。

## 監査の限定修正

- `worker_wif_enabled`だけ、承認入力がboolean falseの場合にboolean falseまたは完全一致の文字列`"false"`を受け入れる。true、`"true"`、大文字、空白、数値、null、containerを拒否する。他の変数はJSON型を含めて一致させる。
- email SES・空ses_domainという既存baselineで、Stateに省略された既知の`ses_domain_verification`だけ、planned null + output no-op/null/null/knownを許容する。任意のnull出力、非null差分、key消失、未知出力は拒否する。
- prior outputsをStateと照合し、planned output集合とoutput_changes集合を一致させる。actionsはno-opのみ、before/afterはStateの既知値（指定SES例外はnull）へ一致し、after_unknownはboolean falseでなければ拒否する。必須fieldを省略したJSONも拒否する。
- 全32 address、before/prior/planned/after、指定2 policy以外30 no-op、既存IAM権限、trust/boundary/OIDC/WIF/runtime/S3属性を引き続き監査する。drift、deferred、unknown、create/replace/destroy、import、address移動は拒否する。malformed unknown maskの0/null/文字列も拒否する。

## 2つのrevisionを結ぶ信頼関係

正式復旧用descriptorはschema 1、kind=`p4-bootstrap-audit-recovery`。`original_source_sha`と`audit_source_sha`を分け、異なる40桁Git SHAを要求する。承認者は両revisionと全hashへ同時に承認する。

元承認descriptor・Plan・show・snapshot・failure・全段階stdout/stderr・backend HCL/metadata・inputs・コピーされた.tf/provider lockのhashを閉じたmanifestへ固定する。元開始journalと元actor inspectもpath/hashを固定する。元descriptorは元実行開始時刻で承認の有効性を確認し、期限を延長・書換えしない。復旧操作は別の新鮮な24時間以内の承認を要求する。

新監査のfull Git SHAと、監査依存11ファイルのGit blob SHA-256を固定する。指定repositoryのclean main、remote main、実行中module bytesを照合する。CRLF/LFはPythonの改行表現としてのみ正規化し、Git blobのhashを記録する。元revisionのbootstrap構成とprovider lockはGit blobから読み、新mainの同構成とbyte-for-byte同一でなければ拒否する。元Planのsourceを新revisionへリラベルしない。

将来生成するbindingはschema 2、kind=`p4-bootstrap-recovered-plan-binding`。元source/Plan/承認/journal/actor/全artifact/State identity/version inventory/input/provider/backendと、新監査source/code manifest/復旧承認/復旧開始journalを結ぶ。既存schema 1の正常Plan bindingへ偽装せず、元runへ書かない。

## 独立した正式復旧経路（今回は未承認・未実行）

`bootstrap_audit_recovery.py`のCLIは`recover`だけを持つ。Plan/Apply/Destroy/repair/force-unlockコマンドは存在しない。実行にはapproved=trueの別descriptor、実descriptor SHA、および対象子プロセスだけの`P4_BOOTSTRAP_AUDIT_RECOVERY_READY=true`が必要。

復旧runは元runと異なるprivate領域に固定し、ancestor/descendantの重なりも禁止する。元journal/ledger、saved Plan、ログ、State、backend設定には書かない。private領域は書込み前にACLをcurrent user/SYSTEM/Administratorsへ制限する。

新しい`bootstrap-audit-recovery-ledger/<canonical namespace hash>`へexclusive/fsyncで復旧開始を保存する。開始済みnamespaceはrun/descriptorを変更しても二重実行を拒否する。元`bootstrap-maintenance-ledger`のplan-startedは保持し、plan-completedを補作しない。

正常経路は、元全artifactのhash/歴史的承認/主体/構成/32資源監査→AWS SDK read-onlyの現actor・canonical State・全32実資源確認→再読取り→元artifactと監査revisionの再照合→新runのreviewコピー・readback・schema 2 binding→新ledgerとrunの完了記録。Plan bytesは読取りだけで、新たなTerraform State/Planファイルを生成しない。Terraform binaryを呼ばず、S3 lockfile Put/Deleteも行わない。

AWS SDKは既存`BootstrapAWS`のread/describe/list/head/simulateガードを使用する。Account/Region/Role一致、State identity・全address・version inventory一致、active S3 lockなし、想定外IAM差分なしが必要。State lockは強制解除せず、read-onlyの二重確認とsingle operator運用を使う。複数clone/端末で同時に操作しない。

失敗・timeout・結果不明なら新しいfailed journalを残して停止する。再復旧、再Plan、再Apply、journal削除、別runでの回避、State修復を行わない。bindingだけ存在し完了journalがない場合もApply検証は拒否する。

## 将来のApply前検証

`validate_recovered_apply`は純粋な検証関数。`verify_apply`はprivate artifactと現AWSを読取り、両方のjournalコピー、全hash、二つのrevision、State/version、全32資源を再監査するwrapperである。どちらもApply・Plan・binding生成・journal更新をしない。

別のfresh Apply descriptorはkind=`p4-bootstrap-recovered-apply`とし、実Plan SHA・実binding SHA・復旧承認SHA・元source・新監査source・両run・Roleを固定する。正常lock、canonical State書込み、指定2 IAM policy更新はこの別承認で明示する。元Planのsource_shaは維持する。

本PRは実Apply controllerを提供しない。通常の`bootstrap_maintenance.py apply`は元のplan-completed/bindingがないため、このfailed Planを受け入れない。将来のcontrollerはこのread-only gateをlocal operation lock内で、saved Plan Apply直前にも実行し、新復旧ledgerへapply-startedをexclusive/fsyncで保存して1回だけ正常locking付きsaved PlanをApplyする設計とする。再Planは使用しない。partial failure時はread-onlyで停止し、成功時は既存`check_applied`とAWS実体・State identity/serial・version inventory・lockを読み戻す。この書込みcontrollerの実装・実行は別レビュー/承認の範囲である。

## 承認段階と費用

1. 今回は修正branch・オフライン検証・Draft PRまで。main merge前に停止する。
2. exact HEAD/baseのmerge承認後、新main SHAへ監査コードだけを再固定する。元source/Plan/承認/State/hashを変更しない。
3. 新main・旧Plan SHA・完全な復旧descriptor hash・新run・single operator・費用を特定した正式復旧1回とschema 2 binding/復旧完了証跡生成の承認を受ける。
4. 正式復旧が成功した後、実binding/review/Plan hashを提示する。Applyは別のcontrollerレビューと限定承認を必要とする。

復旧に必要なAWS書込みは0。S3 Get/Head/List等の読取り費用だけで、以前の公式Price Listに基づく5000 requestsをTier1扱い・64MiB egress・64KiB storage/1か月の保守枠でも約0.031 USD（税別）、上限案0.05 USD＋税。これは請求の強制停止機構ではない。実行前に費用・State・lock・主体を再確認する。GitHub課金は別で、Apply時の費用・書込みは復旧承認に含めない。
