# Bootstrap復旧PlanのApply controller（実行未承認）

この実装は正式復旧で生成されたschema 2 bindingを使う将来のApply経路である。
コード実装・FakeProvider検証・PRはApply承認ではない。今回、実TerraformやAWS書込みは実行しない。
既存の正常Plan用`bootstrap_maintenance.py apply`を迂回・変更せず、旧失敗journal/ledgerを保持する。

## 2つの実行元と独立承認

`bootstrap_recovered_apply.py`のCLIは`apply`のみ。次の両方のfreshな完全SHA承認と、
子プロセスの`P4_BOOTSTRAP_RECOVERED_APPLY_READY=true`を要求する。

1. 既存`p4-bootstrap-recovered-apply` descriptor。元Plan/両revision/両run/復旧承認/bindingのSHA、
   Role、通常S3 lock書込み・canonical State書込み・指定IAM policy更新、費用を明示する。
2. 新`p4-bootstrap-recovered-apply-controller` envelope。schema_versionは厳密なinteger 1、
   kind、approved=true、expires_at（24時間以内）、cost_cap_usd="0.05"、controller_source_sha、
   controller_code_sha256、controller_repository、audit_repository、apply_approval_sha256、
   apply_run_path、terraform_path、terraform_sha256、provider_filesを全件固定する。未知fieldは拒否。

controller_repositoryはcanonical共通Git dir内のcleanなレビュー済みGit revision。
topic branchのimmutable SHAも明示承認できるが、controller Git blobとloaded bytesの一致が必須。
audit_repositoryは復旧時のclean main・audit_source_sha・remote mainを既存のcode_identityで検証する。
両checkoutはcanonical repositoryの共通Git dir/private rootを共有し、既存11監査moduleのbytesを維持する。
復旧のaudit_source_shaを新controller SHAへ書換えない。

mainが復旧revisionから進むと、既存code_identityのremote main Gateが成立しなくなる。
このPRをmainへmergeする前にもその影響をレビューする。Gateを削除したり別clone/path overrideで回避したりしない。
現行契約ではmainを復旧revisionに保ち、別のreviewed controller revisionを明示承認する実行形態を用いる。
将来mainへ統合したうえで実行する場合は、binding/revisionの別契約レビューが必要で、このPRの承認だけでは自動移行しない。

Terraform実行ファイルは絶対path/完全SHAとversion 1.14.9を固定する。
provider_filesは元runのdata/providers以下の閉じたhash manifestで、hashicorp/aws 6.64.0、
WindowsまたはLinux amd64の実行ファイルと任意のLICENSE.txtだけを許す。cacheの追加・変更・symlink/junctionを拒否する。
provider lockを変更せず、init/download・再Planを行わない。正式承認前にruntime manifestをレビューして固定する。

HashiCorpの[backend仕様](https://developer.hashicorp.com/terraform/language/backend)では、saved Plan適用は
Plan内のbackend設定を使い、ローカルbackend metadataは実資源Stateとは別物と説明されている。
[saved Planの説明](https://developer.hashicorp.com/terraform/tutorials/cli/plan)はprovider versionの固定も説明する。
ここから同じbackend metadata/provider cacheの新run利用を設計したが、FakeProviderだけではnative Terraformの
互換性を証明しない。今回のオフラインPASSを実Apply成功保証とせず、実行前のruntimeレビューを残す。

## 1回限りの実行・保全

ローカル承認・全historical artifact・schema2 semantic binding・両側完了journal・controller/audit code・
runtime/cache・未使用出力pathを、SDK/実Terraform到達前に検証する。未承認時にSession/SDK/networkへ到達しない。
canonical bootstrap-operation.lock内で再検証し、復旧namespaceへapply-startedをexclusive/fsyncで保存する。
namespaceにunknown/apply開始/完了/失敗記録があれば開始しない。別run/descriptorで再試行しない。

新しいprivate apply runへ構成/provider lock/backend metadataと承認されたprovider cacheをコピーする。
元Planはコピーも再生成もせず、元の絶対path・同じ完全SHAをApply直前に確認して使用する。
TF_DATA_DIRは新runのdataに限定し、元data・構成・Plan・journal・復旧bindingに書かない。
実行環境は既存credential_environmentで固定し、外部TF_*/TERRAFORM_*/endpoint overrideを拒否する。
子プロセスではCHECKPOINT_DISABLE=1を設定し、Terraformのバージョン通知用外部照会を抑止する。

許すTerraformコマンドはversion -json、pre/postのstate pull、show -jsonと、1回の
`apply -input=false -lock=true -lock-timeout=0s <元saved Plan絶対path>`だけ。
init/plan/destroy/force-unlockや任意引数はprocess境界で拒否する。
stdout/stderrは新runへexclusive保存。timeout/nonzero/結果不明を成功扱いせず再呼出ししない。

現actor/State/全32資源を確認し、Terraform version・既存backend・State pull・saved showを照合する。
Apply直前に現State/主体/全32資源、全旧artifact、binding、Git/code、runtime、期限、current ownerの開始journalを再確認する。
このlock ownerだけが自身の同一開始journalで最終再検証できる。foreign startを無視・削除・置換しない。

成功後は既存check_appliedでlineage保持・serial前進・同32 address・指定2 policy以外の不変を確認し、
version inventoryの旧version保持、新Versionのみ追加、IAM/全資源、post State pull、二重State照合、
元artifact保全と新構成不変を確認する。新runと復旧namespaceへ両側完了journalを保存してlocal lockを解放する。
lock解放失敗、片側完了、post-readback失敗もfailed記録を保持して成功とみなさない。
失敗時はreader.diagnoseだけを使い、AWS/State/lockの修復・解除や再Applyを行わない。

## 検証と次の承認境界

単体テストは合成State・FakeProvider・fake subprocessだけを使い、全テストで実Session/SDK/socketを禁止する。
正常1回、承認/期限/書込みflags/hash拒否、namespace競合、loaded code、command lock、timeout/partial failure、
post State不整合、片側完了journal、lock解放失敗、別run retry拒否を重点検証する。
既存復旧/maintenanceの回帰を併せて実行する。

認証・State・IAM書込みを扱うcontrollerなので、低リスク自律mergeの対象にはしない。
Draft PRとオフライン監査までを提示し、controllerレビューと、実binding/runtime/descriptor/費用・回数を固定した
別のApply承認を待つ。実AWS副作用のない今回のCI成功から書込み承認を推定しない。
0.05 USDは既存契約値であり請求の技術的強制停止機構ではない。
