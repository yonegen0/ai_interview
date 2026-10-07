# 質問管理・デフォルト15問の実装検証

2026-10-06。対象はローカルの実装変更とAWS非接続の検証。
Git HEADは既存mainのまま、今回の変更は未commit／未push。
GitHub上で今回の変更を含むCI runは起動していない。

## 実装内容

- 初期15問をBackend JSONから共有し、通し／10カテゴリの練習、一巡終了を追加。
- 新規練習ごとに質問一覧を読み取り、保存の際に版を確認して質問スナップショットを確定。
- ADMINの本文・カテゴリ編集、追加・削除・上下移動、保存確認、競合比較、保存結果再確認を追加。
- 一覧と更新・再送判定記録を同じトランザクションで保存。一般APIの一覧書込みをIAMで許可しない。
- EMAIL_OTPログイン、タブ内保持、token更新の単一実行、401の1回更新・同一要求再送、ログアウトを追加。
- Client ID＋subで下書き・操作復旧・管理者編集を分離。ログアウト後の遅延認証応答を拒否。
- 新規Sessionは一巡で終了。旧Sessionは循環、旧評価・保存済み応答は読取り互換を保持。
- 旧Mockの21問を復旧用に保存し、version1原本を残してversion2へコピー。不整合時は復旧を拒否。
- 専用admin Lambda／alias／Role／LogGroup／Route、manifest v3、v2読戻し互換を追加。
- P4 package CIのimport検査を4 handlerと15問へ拡張。

API・制約は[Frontend API契約](FRONTEND_API_CONTRACT.md)を正本とする。
管理者の更新・再送記録は専用型で検証し、既存Session応答用の冪等記録を流用しない。

## 検証結果

| 検証 | 結果 |
|---|---|
| Backend通常suite | 890 passed／57 deselected。サイズ超過・破損データ拒否を含め成功 |
| Frontend unit＋Storybookブラウザ | 全体372 passed、その後に保存不可の境界1件を追加。最終unit165 passed、Storybook208件成功 |
| Playwright E2E | 13 passed。管理者ログイン・編集保存・既存質問保持・新規反映・最終問・再挑戦・USER拒否を確認 |
| 画面幅 | 375／768／1280pxで横溢れなし。改行質問と管理画面をPNGで確認 |
| Frontend lint／typecheck | 成功 |
| 本番／Mock静的ビルド | 成功。login・admin/questions・既存練習Routeを静的生成 |
| Storybook静的ビルド | 追加の認証・管理画面を含め成功 |
| Terraform offline | 4 root validate成功、service mock34／bootstrap mock1成功 |
| Linux展開ZIP import | WSL Ubuntu、CPython3.14.4、x86_64で4 handlerと15問の読込成功 |

Linux検証は既存uv.lockの12固定依存をhash検証付きで取得し、検証専用ZIPから実importした。
socket接続とbotocore送信を禁止し、アプリ・SDK・Pydanticの読込み元が展開ZIP内であることを確認した。
ZIPはzero SHAの検証用manifestと`release=false`で区別し、配備Artifactとして使用しない。
既存のAWS配備Artifactをbuildし直したものではなく、S3へuploadしていない。

TerraformはAWS認証・実tfvars・State・既存`.terraform`を除外した一時コピーで実行した。
providerのLinux checksum補完はコピーだけで、元lockfileは保持した。
Windows sandboxでの子プロセス／private ACL制限による試験失敗は、元の失敗物を残し、
新しい検証領域で制限外の非接続試験を実行した。既存のACL・過去証跡は変更していない。

実行ログ、検証専用ZIP、manifest、Linux結果はGit管理外の`.p4-artifacts/question-management-*`に保管。
画面PNGはFrontendのGit管理外`playwright/.cache/question-management/`に保管。
旧共通fixtureは`contracts/backend-fixtures.v1.json`に保全し、新契約fixtureとは分けた。

## 実AWSの状態と残る工程

新機能はAWS未配備。AWS資源・運用State・Cognito Group・実ユーザー・SNS・SESを変更していない。
新しいAWS saved plan、apply、実OTP送信、新負荷試験、Artifact uploadは実行していない。
既存devの正式ステータス`P4_DEV_CLOSED_PERFORMANCE_REVIEW_REQUIRED`と
`POST_DEPLOY_PERFORMANCE_VALIDATION_REQUIRED`を維持する。既存のAPI p95 Gate FAILを改訂しない。

後続では新構成をclosedで配備して4 Lambdaと5 aliasを読み戻し、その後に一時検証する。
実OTP完了、JWTとADMINの実認可、DynamoDBのIAM実効許可・拒否、保存と練習の実機接続は未検証。
adminを含む新構成のdev検証Alarmは17件、closedでは0件となる。過去の14件Closure証跡は変更しない。
Enablementには[条件付き自動Closure承認](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)を同時に含める。
基盤配備の新規資源はClosureのホワイトリスト承認とは別に監査し、実行済みplanを再使用しない。
