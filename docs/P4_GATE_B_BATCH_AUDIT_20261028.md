# Gate B一括オフライン監査・実行前の修正

2026-10-28 JST。監査基準mainは `fa8d9333d17f915a08833f8ae3774eae02a0b9be`。
本資料はAWS接続、dispatch、設定変更、Plan/Apply、push/mergeの承認ではない。

## 確認結果と最小修正

API `2022-11-28` の実GETでは、dev-plan/dev-applyともdeployment branch policyは
`total_count=1`、`name=main`、`type=branch`。custom=true/protected=false、
admin bypass不可、manualモード、両Environmentのreadiness全4項目falseを確認した。
[公式サンプル](https://docs.github.com/en/rest/deployments/branch-policies?apiVersion=2022-11-28)
のtype省略だけでは不具合と判定しない。type欠落をbranchと推定する変更は行わない。
欠落・余分なpolicy・tag・不正typeと両保護モードの回帰試験を追加した。

Stage復旧専用 `apply_process()` は通常の `terraform_dev.run()` を経由しないため、
GitHub Environment読取り用App tokenをTerraform子プロセスへ渡していた。
修正はPopenに渡す環境のコピーから `P4_ENV_READ_TOKEN` を除く1行のみ。
親環境、短期AWS資格、正常/異常終了の記録・停止条件は保持する。
合成Popenで旧コードの正常/非正常両ケースを失敗再現し、修正後の拒否を検証した。
実token漏洩の観測や実Applyの失敗原因確定を意味しない。

別の確定不具合として、未承認OIDC準備資料のreader hashはWindows CRLF bytesを
使用していた。Linux実行時のhashは固定commitのGit blobから計算する必要がある。

- CRLFの誤った期待値: `0905af675f05fba332a7a547355b3548bfac3809c9a3e68d771655011708c982`
- Git blob/LFの正しい期待値: `ba521a13091a13ea3d0ada95112446390babe01f15f0631ed12f868e1a247df5`

これはローカル承認準備資料の問題で、reader実行コードの変更は不要。
旧資料を上書きせず、正しいhashを使用した新資料へ引き継ぐ。
承認全文bytesの改行正規化や、実行後resultのhash書換えで回避しない。

## 再利用した証拠

- [GitHub-only Run40593628921](https://github.com/yonegen0/ai_interview/actions/runs/40593628921)
  は基準main/Attempt1成功。OIDC jobはskippedであり、OIDC成功とは数えない。
- State13限定監査は42 SDK/42 HTTP、変更0、before/after一致、lock不在、4入口閉鎖、
  既存Artifact/4Lambda/5aliasとplan/artifact-plan IAM構成一致。private hash連鎖を
  オフライン照合して再利用し、新規AWS読取りは行っていない。
- [旧OIDC Run40066655842](https://github.com/yonegen0/ai_interview/actions/runs/40066655842)
  は旧source `116a42b0519af31e3ef0efe4a24aca60f46f9524` で両job成功。
  既存ZIPのhashはGitHub metadataと一致し、全20check/4sessionを再検証した。
  readerとbootstrapのtrust/policyのGit blobは基準mainと同一。
  Workflow条件・setup-uv/Python指定は変わっているため、現SHAでの実行完了とは扱わない。
- 旧Plan001/002はAttempt1失敗・承認消費済み。再実行しない。
  元Applyの正常終了はUNKNOWNを維持する。

## 実行前の境界

この修正をPlan003の前に統合し、保護されたmainの実際のSHAを確認する。
旧承認・旧descriptor・旧sourceのhashをそのSHAへ書き換えたり転用したりしない。
現SHAでの限定OIDC実証を行う場合は新しいsource/reader/integrity/hashと72時間窓を発行する。
未承認の旧OIDC案は上記reader hash不一致もあるため実行しない。

Plan003の最終承認は実効OIDCとfresh preflight成立後に別発行する。
Stage形式のみadd0/change1/destroy0/replace0、通常refresh、State13固定、既存Lambda
Artifact固定再利用、未知値・他drift・lock拒否、成果物5個のVersionId/hashと
独立readback、readiness false復帰を維持する。Terraform1.14.9/dev Provider6.65.0。
PythonのSDK512/HTTP512にTerraform Go通信は含まれず、全AWS通信hard capではない。

新saved Planと同じsource/bytes/hashへのApply専用承認が別途必要。
Apply実終了コード、receipt、State/Stage/4入口/readiness読戻しが揃うまでGate BはNOT_READY。
失敗/cancel/UNKNOWN/Artifact欠落/Matrix部分成功でPASSへ進めず、無断再実行しない。
PR43 Draft/HOLD、実AI、Hosting、外部公開は対象外。

## 検証

ネットワーク禁止fixture下の重点Backend試験574件、証跡暗号化/OIDC等40件、
独立受入の既存13件と追加16件を確認した。旧token伝播の失敗再現2件も保存。
暗号化試験の初回9 setup errorは既存OpenSSLのPATH不足であり、PATH修正後15件成功。
ローカルMock・hash照合・過去CIは、現在のAWS権限/Plan/Applyの成功保証ではない。
