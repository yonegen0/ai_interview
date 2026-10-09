# test閉鎖・固定Version Stateのread権限修正案 — 2026-10-09

本書はTerraformコードのレビュー用。IAM実環境変更、bootstrap plan/apply、test作成/閉鎖/再開の承認ではない。PR #1のsource `f1756a79af4c115da0d04dfe911ab998ea45d646` を基に独立branchで準備した。

## 確認した不足

実 `ai-interview-ci-test` policyの読取りとガードの呼出しを照合した。既知の `dynamodb:Scan` と `lambda:GetFunctionEventInvokeConfig` に加え、State accessも不足する。

- `test_closure_guard.verify_quiescent` はbase tableを全ページConsistentRead Scanし、全5aliasのasync lifetimeを取得する。Deniedを空の観測値として扱わない。
- `deployment_guards.read_state_snapshot` は `test/<run>/terraform.tfstate` を固定VersionIdで取得する。既存State policyのtest keyは `runs/*` で、canonical keyと一致しない。
- 固定VersionId読取りは [S3 GetObjectの仕様](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)により `s3:GetObjectVersion` が必要。
- [HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)は、存在しないobjectでListBucketがあれば404、なければ403を返す。lock不在の確実な判定にbucket metadata readが必要。403を不在扱いする変更は行わない。

## 実装差分

既存 `aws_iam_role_policy.tests` (`synthetic-tests`) に次の5statementを追加した。さらに実plan/deploy Roleのpolicy読取りでcanonical dev Stateの `s3:GetObjectVersion` Allow不足を確認したため、両Roleの `state-and-artifacts` policyに**exact `dev/terraform.tfstate` のGetObjectVersionだけ**を追加した。Scan/async readはtest Roleだけ。artifact Role、OIDC subject/audience、runtime boundary、WIF署名条件、既存write権限、backend/providerは変更しない。

| Sid | Action | Resource |
| --- | --- | --- |
| TestDrainInventory | dynamodb:Scan | Tokyo/対象Accountの `table/ai-interview-test-*-main` だけ。dev/P3/indexは追加対象外 |
| TestDrainAsyncLifetime | lambda:GetFunctionEventInvokeConfig | test API/Admin/Workerのlive、Dispatcherのstreams/recovery、計5aliasだけ |
| TestStateAbsenceRead | s3:ListBucket | canonical State bucket 1件。不存在lockのHead判定に必要。bucket内のkey metadata列挙は可能になるため、この影響も実変更のレビュー対象 |
| TestVersionedStateRead | s3:GetObject, s3:GetObjectVersion | `test/*/terraform.tfstate` だけ。dev Stateやその他object本文は追加対象外 |
| TestLockRead | s3:GetObject | `test/*/terraform.tfstate.tflock` だけ |

ListBucketのprefix条件付き許可だけをlock Headの404保証として扱わない。追加statementにResource `*`、Invoke、DDB書込み、State書込み、PassRole、trust変更はない。既存policyに元から存在するwrite権限は保持する。

[Lambda authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html)でGetFunctionEventInvokeConfigのfunction resource対応を確認した。対象runが承認された後は、Account/Region/run/5aliasを実manifestと照合する。本案は既存test prefixの運用に合わせたnamespace許可で、run単位の独立承認やwriter停止proofを置き換えない。

## 検証

AWS credential/metadata/backendを除いた新規コピーで、Terraform 1.14.9の4root validate PASS、service47 + bootstrap3 = **50 mock PASS**。新mockはtest-only Scan、正確な5alias、固定Version State/lock、他CI Roleへの非追加、OIDC trust/runtime boundaryの不変を検査する。既存のcombined inline policy quota（10,240文字）試験もPASS。Provider lock/version/constraintsを変更していない。

実IAM AssumeRole/実効権限/実ガード受入は未実施。policyのstatic Allow確認はSCP、session policy、resource policy、boundaryを含む実効権限の代用ではない。

## 残る配備条件

1. この独立branchをレビューし、別承認でmainへ反映する。
2. bootstrapの現在State/入力/Role/trust/boundary/WIFをread-only照合し、正式runbookで新saved planを作成、全件差分・SHAを固定する。想定は既存test inline policy1件とplan/deployのState policy2件、計3update、他baseline no-op。実planはまだない。
3. Account/Region・plan SHA・policy差分に結合したIAM変更承認を得てから1回applyし、読戻しする。今回はapplyしていない。
4. 専用testに対して実ガードを受入する。新readが揃っても、writer停止、ledger、async lifetime+timeout、全ページScan、15分proof、39 Alarm限定delete、再apply禁止を維持する。

**canonical test Stateのwrite/lock権限は本案では追加していない。** 現在の `runs/*` write scopeと `test/<run>/terraform.tfstate` の不一致により、このtest Roleをそのまま正式test applyへ使えるとは判定しない。必要なら承認runのexact State/lockに絞った別のbackend write案をレビューする。read不足の解消を理由にwrite scopeやruntime boundaryを自動拡張しない。dev固定Version State readの実効権限も、案の実適用後に実行Roleごとに別途照合する。

State keyの変更/migration、State surgery、ガードの403無視やScan省略は行っていない。必要な観測を証明できなければ、test Alarm削除は引き続き禁止する。
