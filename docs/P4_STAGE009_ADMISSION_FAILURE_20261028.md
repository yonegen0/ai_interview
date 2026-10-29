# Stage009監査・実行前拒否と公開準備

2026-10-28 JST。**Gate B / 公開はNOT_READY**。以下は実測とローカル検証の記録であり、
新しいPlan/Apply・実AI・入口開放・Hosting公開の承認ではない。

## 成功した独立Plan監査

- sourceは `c09051a6d3a6d497fdcaa264ed7e061bd9a2b89e`。
- [Stage Plan Run40680275113](https://github.com/yonegen0/ai_interview/actions/runs/40680275113)
  / Attempt1は成功。Saved Plan SHA-256は
  `a4d14d2b3784087ef8ad324765763dbefefd37d4e55104771d667d7a6bf43dc3`。
- Terraform1.14.9 / dev AWS Provider6.65.0。既存Artifactを固定再利用し、新Planは生成しなかった。
- 独立S3読戻しは36 SDK / 36 HTTP、再送・書込み0。State14のlineage/serial/VersionId/hashは前後一致、
  lock不在、API/Worker/Streams/Scheduler閉鎖。Bootstrapのserial5とは別のState。
- 資格情報なし・外向通信遮断の`terraform show`でも同一バイナリから同じJSONを確認。
  全77資源はMATCH76 / 意図したStage形式更新1 / 不明0。
  add0/change1/destroy0/replace0、IAM・認証・Lambda・データ保存の変更なし。
- 成功Runの公開Artifactは暗号化journalとredacted summaryのみ。平文Plan/Stateを公開していない。

元の封印済みreaderはserial13を固定していたため、そのまま実行しなかった。
元パッケージを保持し、同一commitのclean worktreeと固定State14を使う補足readerを別保存した。
コード差分は固定scopeとserial14の完全一致検査だけで、ネットワーク禁止37件PASS。
別保存の実行wrapper試験70件もPASSしたが、次の標準Workflow契約との結合試験が欠けていた。

## 新たに承認されたdispatchの結果

所有者は上記Saved PlanのApply1回と事後検証を明示承認した。
[Apply Run40686131459](https://github.com/yonegen0/ai_interview/actions/runs/40686131459)
/ Attempt1は**初期preflightで失敗**。Terraform Applyの起動・正常終了はない。

Codexがローカル承認期限を元scopeの期限へ切り詰めたことで、発行からの期間が
71時間7分30秒になった。一方、標準`ci_identity.standard_context`は正確な72時間を要求する。
ローカルwrapperの「72時間以下」検査と一致せず、AWS準備より前に拒否された。
実inputsを標準関数と`ci_deploy.preflight`へ渡すネットワーク禁止試験で
`StandardApprovalExpiredOrNotIssued`を再現した。日時の書換えや認可条件の緩和はしない。

WorkflowのBackend/Terraform offline検証は成功、Apply stepは失敗。
当時のApplyには標準の有限診断がなかったため、公開ログは`P4CiDeploymentFailed`のみだった。
このPRの修正は標準Applyにも有限reasonを出し、未観測の後段process状態を`null`にする。
承認・72時間・履歴消費・IAM・AWS処理は変更しない。関連424件とRuff/整形がPASS。

## 失敗後の実AWS読戻し

承認に含まれる独立事後診断を24 SDK / 24 HTTP、再送・AWS書込み0で実施した。

| 対象 | 実測 |
| --- | --- |
| dev State | serial14、全77資源、同じlineage/VersionId/hash、取得前後不変 |
| State lock | 不在 |
| Stage実形式 | 更新前4項目のまま |
| API/Worker/Streams/Scheduler | 全て閉鎖 |
| S3 receipt | apply-started / apply-completed / deployment は固定keyへのHEAD404で不在 |
| GitHub readiness | dev-plan/dev-applyの全4項目false、cleanup error0 |

receipt不在だけで未起動を推定せず、実入力での最初のpure preflight拒否と合わせて判断した。
旧Apply008の失敗、さらに古い元Applyの正常終了UNKNOWNは履歴のまま保持する。
再Apply・State編集・unlock・新Plan・入口開放は実施していない。

最初のdispatchは失敗を含め承認を消費する。同じPlanを再送すると既存の履歴検査が拒否するため、
この承認/Planで再実行しない。次回は新source/固定State/実行窓に対する新Planの承認を準備し、
そのSaved Planの独立監査後に別のApply承認を受ける。新たなローカルdispatch前ガードは
標準関数そのもの、3600秒の余裕、scope期限、消費済み対象拒否を確認する（15件PASS）。

## 独立して完了した公開準備

Frontendの旧ZIPには`/dev`のないAPI URLが残っていた。実行器が依存取得前に捕捉した環境を
設定修正後も使ったことが時系列と実装から強く推定される。旧ZIPは公開対象から除外し、保全した。
修正済み設定で別worktreeから本番Static Exportを再生成した。

- 新ZIP SHA-256: `79a649dc2c59d963e2390bcf9e3fb58ea535c7f7280c4803843e14e2280b447d`。
- 76ファイル、7経路、正確なAPI URL/Cognito設定、MSW除去、ZIP/設定hashをオフライン照合。
  再実行可能な検査で旧ZIP拒否・新ZIP受入を確認した。
- Chromium mobileで本番ログイン画面表示PASS、外部通信/ServiceWorker/ブラウザ例外0。
  同一sourceの[Frontend CI](https://github.com/yonegen0/ai_interview/actions/runs/40679212812)
  はlint/型/Unit/Storybook/E2E/両build/依存audit成功を再利用した。
  ローカルNode24.22.1とCI22.23.4の差を記録。実認証・Hostingは未実施。

Backend/Bedrock重点102件、source-plan契約53件、Ruffと260ファイル整形がPASS。
Windows全suite初回は3314 PASS/54 FAIL/9 ERROR。子プロセスのPSModulePathとOpenSSL PATHを
補正して診断67件・暗号化15件がPASS、残14件はPOSIX専用テストのWindows制約。
全suiteのWindows成功とは報告しない。同一sourceのLinux CIは成功。
400件のMemoryRepository/FakeProviderローカルフローが完了しp95は49.740ms。
これは実AWS/実AI性能を保証せず、既存AWS cold p95 2003.466msのFAILは維持する。

Bedrock ProviderコードとTerraform opt-inは存在するが、現Worker環境/Boundaryは未設定。
現標準経路は閉鎖契約としてprovider mapを空へ固定し、canonicalなruntime設定配備経路が不足している。
閉鎖維持の入力候補・最小IAM projection・別descriptor/Plan/Apply/receipt/readback要件をローカル準備した。
既存Stage guardを緩和して配備しない。実GetInferenceProfile/有料推論/30人実測、
実Cognito/API受入、HTTPS origin/CORS確定、Hosting/公開は別工程で未実施。
