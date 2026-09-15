# P4 IAM静的照合（2026-09-14）

対象は閉鎖状態の初回dev配備。Terraform mockはAWSの認可評価を実行しない。
実機の許可・拒否試験、組織SCP、Permission Boundaryとの実際の交差、quotaは未検証。

| 対象 | 照合・実装内容 | 実機で確認すること |
|---|---|---|
| DynamoDB Transaction | 内部Put/Get/ConditionCheckのActionで許可。架空のTransactWriteItems権限に置換しない | 実Transaction成功・条件拒否、別Table拒否 |
| WorkIndex/Streams | runtimeの対象Table配下index/stream ARNとboundaryの対象を照合 | Query、Streams読取り。Scanや別資源は拒否 |
| SQS | runtimeは送信・受信・削除・属性読取り。配備は対象prefixのQueue管理 | dev/testの分離、他Queue拒否 |
| Scheduler | schedule/group ARNを限定し、PassRoleはruntime Roleとサービスに限定 | recovery aliasのInvoke、別Role拒否 |
| Lambda mapping | 作成等のResource `*`にFunctionArn条件を併用 | 別prefix mapping操作拒否 |
| API Gateway V2 | 管理APIのHTTP動詞、ApiNameとProject/Environment条件 | API作成、子Route等の更新、他project拒否 |
| Cognito | Pool管理・Client管理を分離。作成時RequestTag、既存PoolはResourceTag | Pool/Client作成、別Pool拒否 |
| Budgets | Describe系APIはViewBudgetへ対応。無効なDescribe系Action名を削除 | Budget作成・通知設定読取り |
| S3 State | State本体と`.tflock`の権限を分離。plan RoleはState本体を書かない | 初期plan、lock取得/解放、saved-plan apply |
| artifact | version付きobject、条件付き作成。不存在確認用ListBucketはplans prefix限定 | journalの新規作成・応答喪失・既存object拒否 |
| bootstrap | OIDC URL/aud、4 Roleの完全一致sub、boundary本文を独立期待値と比較 | 実IAM応答との一致、SES検証状態 |

`runtime_boundary`はruntime Roleへ付ける境界であり、4つのCI Roleへ同じ境界を付ける設計ではない。
CI Roleに想定外のboundaryが付いていればbootstrap読戻しは失敗する。
bootstrap mockでは、Roleごとのinline policy合計が10,240文字以下であることも確認する。

IAMはPK条件等を制限できても、業務上のSK、rev、terminal/started、所有者と資源IDの関係を全て表現できない。
これらは既存アプリ・Repositoryの条件検証を維持する。静的IAM試験でアプリ試験を代替しない。
同じdev Subjectを信頼する4 Roleは、人の分離を保証しない。main/workflow変更権限を配備権限の一部として管理する。

## 公式資料

- [DynamoDB TransactionのIAM](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html)：Transaction内の操作と基礎Actionの対応。
- [DynamoDB Action/Resource](https://docs.aws.amazon.com/service-authorization/latest/reference/list_dynamodb.html)：Table/index/streamとActionの対応。
- [SQS Action/Resource](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sqs.html)：Queue ARNと送受信・管理Action。
- [Scheduler Action/Resource](https://docs.aws.amazon.com/service-authorization/latest/reference/list_scheduler.html)：schedule/groupとPassRole。
- [Lambda権限例](https://docs.aws.amazon.com/lambda/latest/dg/permissions-user-function.html)：mapping作成のFunctionArn条件。
- [API Gateway V2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html)：管理Resourceと条件キー。
- [Cognito User Pools](https://docs.aws.amazon.com/service-authorization/latest/reference/list_cognito-idp.html)：Pool/Client管理Action。
- [IAM](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam.html)：PassRole、PermissionsBoundary条件。
- [Budgets](https://docs.aws.amazon.com/service-authorization/latest/reference/list_budgets.html)：DescribeBudget/Notifications/Subscribersに必要なViewBudget。

この照合はAWSの実機smoke成功ではない。初回実行時に権限不足が判明した場合は、
無条件な`*`権限へ広げず、固定分類とprivate記録から対象操作を特定し、新planをレビューする。
