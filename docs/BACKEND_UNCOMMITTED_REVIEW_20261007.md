# Backend未コミット差分のファイル別レビュー

B1〜B4は修正済み。[修正内容・回帰テスト・最終検証結果](BACKEND_REVIEW_FIXES_20261007.md)を参照。
以下は修正前の記録。行番号とGit管理外の再現スクリプトも修正前の状態を示す。

2026-10-07。比較元HEAD: `ded1d50cd097fa9fcfd780649608ab74049a4bc5`。
対象はbackend配下の未コミット28ファイル。内訳は処理を含むPython 17、テスト9、質問データ1、README 1。
ステージ済み差分はなし。追跡済みの実装・テストを修正せず、各ファイルの差分と呼出先・保存形式・API契約を確認した。

修正対象は4件（P1 1件、P2 2件、P3 1件）。B1の実AWSへの影響は外部の実測報告とコードからの推定であり、今回AWSへ接続した結果ではない。

## 指摘

### B1 — P1: API Gatewayが渡す角括弧付きgroup文字列を解析する

対象: [api/admin.py](../backend/src/interview_backend/api/admin.py#L18)（18〜23行）。
関連: [test_question_management.py](../backend/tests/unit/test_question_management.py#L106)。

`is_admin`は`[`で始まる文字列をJSON配列と仮定する。
`[ADMIN]`や`[USER ADMIN]`はJSONではないため、ADMINが含まれていてもFalseとなり、管理APIが403を返す。
ローカル再現で`[ADMIN]`、`[USER ADMIN]`、`[USER, ADMIN]`はいずれも403、`["USER","ADMIN"]`は200となった。

HTTP API JWT authorizerについて、実エンドポイントを観測したライブラリ作者の記録には、
配列claimが`[Admins Readers]`のような空白区切りの文字列で渡ると記載されている。
これは作者自身の観測記録で、AWSの保証仕様ではない。
[実測記録: The claims the handler receives](https://yulinsim.dev/services/apigatewayv2/#the-claims-the-handler-receives)。
AWS提供サンプルでも、別構成のREST APIについて角括弧付きのgroup文字列を再正規化している。
[AWSサンプルの認可互換処理](https://github.com/aws-solutions-library-samples/accelerated-intelligent-document-processing-on-aws/blob/main/docs/migration-appsync-to-rest.md#4-security--rbac-parity)。

このHTTP APIの観測形式が本構成でも使われる場合、管理者は一覧取得・保存の両方を利用できない。
現テストは配列、JSON配列文字列、裸のADMIN、カンマ区切りだけを使うため検出しない。
信頼済みauthorizer claimの形式を正規化してから、ADMINとの完全一致で判定する必要がある。
実接続試験ではADMINのみ／USERとADMINの両方／USERのみを確認する。今回その実AWS試験は行っていない。

### B2 — P2: 一覧のサイズ判定に回答受付後のSessionサイズを含める

対象: [repositories/domain.py](../backend/src/interview_backend/repositories/domain.py#L220)（220〜229行）。
関連: [repositories/codec.py](../backend/src/interview_backend/repositories/codec.py#L288)、[accept_once](../backend/src/interview_backend/repositories/domain.py#L263)。

一覧保存時に検査するSessionは`active=None`、`version=0`である。
350KiBの上限ぎりぎりの一覧を保存すると、新規Sessionの作成は成功するが、
回答受付でactiveAttemptを追加したSessionの保存が`ItemTooLarge`となり500を返す。
一覧を小さくし直しても、すでに作成したSessionはスナップショットを保持するため復旧しない。

再現は51問。先頭50問の本文を各「あ」1,000文字、最後を「あ」184文字、ownerを36文字とした。
検査用Sessionは358,397bytes、上限は358,400bytes。
管理保存200 → full練習開始201 → 最初の回答POST 500となる。
MemoryとDynamoDB adapterのスクリプト化された読取りで同じ結果を確認し、Attemptは作成されず、DynamoDB側の書込み送信も0件だった。

SessionのactiveAttempt・更新カウンタ等に必要な容量を事前に確保する必要がある。
「上限を超えた一覧を拒否する」試験に加え、「上限内で受理した一覧で回答・評価・次問まで進める」試験が必要。

### B3 — P2: 管理保存と既存POSTの冪等キーの識別範囲を契約と一致させる

対象: [repositories/domain.py](../backend/src/interview_backend/repositories/domain.py#L172)（172〜184行）。
関連: [codec.key](../backend/src/interview_backend/repositories/codec.py#L245)、[API契約の冪等性](FRONTEND_API_CONTRACT.md#冪等性競合)。

既存のPOSTは`IdempotencyRecord`、管理保存は`QuestionBankChange`だけを検索する。
したがって同じJWT sub・同じキーでも、`POST /sessions`と`POST /admin/question-bank`を両方実行できる。
API契約131行の「内容や操作先が異なる同一キーは409」と一致しない。

同じowner・キーで練習開始201の後に管理保存200となり、一覧が版1へ更新されることを確認した。
管理保存を先に実行した場合も管理保存200・練習開始201となる。
誤ったキー再利用を競合として止める契約上の保証が、新しい管理ルートでは働かない。

管理保存専用の記録型を維持しつつ、キーを予約する範囲とAPI契約を整合させる必要がある。
管理APIのIAMは質問管理partitionに限定されているため、共有の予約方式を採用する場合はIAMとの整合も必要。
識別範囲を意図的に分ける設計なら、その例外を契約へ明記して両方向の試験で固定する。

### B4 — P3: expectedVersionの整数値をJSON表記によらず照合する

対象: [models/public.py](../backend/src/interview_backend/models/public.py#L158)（156〜159行）。
関連: [Frontend bankSaveSchema](../frontend/src/lib/api/schemas/index.ts#L137)、[既存scoreの整数値変換](../backend/src/interview_backend/models/public.py#L244)。

Frontendの`z.number().int()`はJSONの`0`、`0.0`、`0e0`を同じ整数値として受理する。
Backendのstrictなintは`json.loads`がfloatへ変換した`0.0`・`0e0`を拒否する。
同じ版0・同じ質問一覧で`expectedVersion:0`は200、`0.0`と`0e0`は400になることを確認した。
FrontendのZodでもこれらの表記を受理することをローカルで確認した。

通常の`JSON.stringify`は整数表記を出すため現在の画面からは起こりにくいが、公開JSON契約の型判定が不一致。
有限の整数値だけをrequest validatorでintへ変換し、bool・文字列・小数の拒否を保つ必要がある。
既存scoreのJSON互換テストと同様に、管理保存の版番号も共通契約試験へ追加する。

## ファイルごとの確認結果

「追加指摘なし」は今回の変更と関連処理を読んだ範囲で独立した不具合を確認しなかったことを示す。
実AWSでの認証・IAM・配備の成功を意味しない。

| # | ファイル | 確認内容・結果 |
|---|---|---|
| 1 | [backend/README.md](../backend/README.md) | 新機能・旧データ互換・AWS未配備の説明を照合。追加指摘なし。 |
| 2 | [skills/p4/ci_deploy.py](../backend/skills/p4/ci_deploy.py) | 展開ZIPのadmin_handler import追加とbuild_lambdaによる収録を確認。追加指摘なし。今回Linux package buildは再実行していない。 |
| 3 | [skills/p4/manifest.py](../backend/skills/p4/manifest.py) | v2/v3読取、v3の4版・5alias・4log group、admin runtime/timeout/hashの検証を確認。追加指摘なし。 |
| 4 | [skills/p4/manifest_alarms.py](../backend/skills/p4/manifest_alarms.py) | admin Alarmの追加、dev activeの17件・closedの0件、v2の既存期待値を確認。追加指摘なし。 |
| 5 | [skills/p4/manifest_checks.py](../backend/skills/p4/manifest_checks.py) | admin/APIのpolicy全件比較、adminの2invoke permission、integration分離、JWT route、4log groupをTerraformと照合。追加指摘なし。 |
| 6 | [src/interview_backend/api/admin.py](../backend/src/interview_backend/api/admin.py) | 認証→ADMIN→routeの順序、本文上限、base64、strict入力、fingerprint、error応答を確認。**B1**。保存のB2/B3、入力のB4にも影響される。 |
| 7 | [src/interview_backend/api/handler.py](../backend/src/interview_backend/api/handler.py) | practice-optionsのログイン、GET/POST引数、no-store、追加codeの固定messageを確認。追加指摘なし。 |
| 8 | [src/interview_backend/application/service.py](../backend/src/interview_backend/application/service.py) | mode省略時の旧fingerprint保持、full/categoryの引渡し、最新bank選択、owner確認を確認。追加指摘なし。 |
| 9 | [src/interview_backend/assets/questions.json](../backend/src/interview_backend/assets/questions.json) | 15問のUUID・順番・10カテゴリ・改行・標準難易度とFrontend共通データを確認。追加指摘なし。 |
| 10 | [src/interview_backend/aws_runtime.py](../backend/src/interview_backend/aws_runtime.py) | admin entry生成、ObservedRepository、admin Metrics、設定失敗時500、既存ApiEntryのgateway/token検証を確認。B1の統合影響あり。独立した追加指摘なし。 |
| 11 | [src/interview_backend/aws_settings.py](../backend/src/interview_backend/aws_settings.py) | adminのaccount/region/table/function、client/pool/api/stageとalias限定を確認。追加指摘なし。 |
| 12 | [src/interview_backend/evaluation/provider.py](../backend/src/interview_backend/evaluation/provider.py) | 新規4カテゴリの評価観点と旧difficultyの保持、質問snapshot由来のprompt生成を確認。追加指摘なし。 |
| 13 | [src/interview_backend/models/internal.py](../backend/src/interview_backend/models/internal.py) | 新規Sessionの有限進行、旧Sessionの循環、bank/change専用型、Stateの保存先を確認。追加指摘なし。 |
| 14 | [src/interview_backend/models/public.py](../backend/src/interview_backend/models/public.py) | modeとcategoryの組合せ、未知field、UTF-16長、case-insensitive UUID重複、旧category読取、進捗3項目を確認。**B4**。 |
| 15 | [src/interview_backend/observability.py](../backend/src/interview_backend/observability.py) | admin dimension追加、固定metric名、storage例外分類を確認。追加指摘なし。 |
| 16 | [src/interview_backend/repositories/base.py](../backend/src/interview_backend/repositories/base.py) | 新規引数・管理保存・選択肢取得のProtocolとMemory/DynamoDBの実装を確認。追加指摘なし。 |
| 17 | [src/interview_backend/repositories/codec.py](../backend/src/interview_backend/repositories/codec.py) | 新規2kindのkey/encode/decode、WorkIndex対象外、bankのstrict検証、旧Session/保存済み応答の互換を確認。B2/B3の関連箇所。独立した追加指摘なし。 |
| 18 | [src/interview_backend/repositories/domain.py](../backend/src/interview_backend/repositories/domain.py) | bank版のCAS、成功再送優先、競合再読取、no-op保存、原子的なbank＋履歴、snapshot、最終問判定を確認。**B2/B3**。 |
| 19 | [src/interview_backend/repositories/memory.py](../backend/src/interview_backend/repositories/memory.py) | 新規collection、owner/keyの履歴分離、CURRENTの格納、copy-on-writeの例外時不反映を確認。追加指摘なし。 |
| 20 | [tests/contracts/test_contract.py](../backend/tests/contracts/test_contract.py) | difficulty要求の型互換と新規開始409の切分けを確認。管理モデルが共通corpusの対象外でB4を検出しない。テスト自体の独立した不具合なし。 |
| 21 | [tests/contracts/test_repository_contract.py](../backend/tests/contracts/test_repository_contract.py) | 次問のあるjob_changeへのfixture変更後も、owner分離・再送・回答競合・次問競合のassertを保持。追加指摘なし。 |
| 22 | [tests/unit/test_application.py](../backend/tests/unit/test_application.py) | 10カテゴリの順次進行、総数・hasNext、最後の409、再挑戦を確認。追加指摘なし。 |
| 23 | [tests/unit/test_durable.py](../backend/tests/unit/test_durable.py) | fixture変更と既存P2 sample roundtrip、size/型拒否、worker/dispatchのassertを確認。追加指摘なし。 |
| 24 | [tests/unit/test_dynamodb.py](../backend/tests/unit/test_dynamodb.py) | 新kindのsnapshot/key/revision/encode、CAS・ACK消失のscripted clientを確認。追加指摘なし。 |
| 25 | [tests/unit/test_p3_completion.py](../backend/tests/unit/test_p3_completion.py) | git statusは変更表示だが、HEADとの内容差分はなし。既存のfeedback整合・予算・期限・破損候補の回帰試験を確認。追加指摘なし。 |
| 26 | [tests/unit/test_p4_manifest_v3.py](../backend/tests/unit/test_p4_manifest_v3.py) | closed v3の読戻し、admin/API権限拡大・route誤接続・invoke policy・版driftの拒否を確認。追加指摘なし。実AWSの代替試験ではない。 |
| 27 | [tests/unit/test_p4_runtime.py](../backend/tests/unit/test_p4_runtime.py) | named-stageの既存route試験をjob_changeへ変更し、再送・評価・次問の検証を維持。追加指摘なし。 |
| 28 | [tests/unit/test_question_management.py](../backend/tests/unit/test_question_management.py) | snapshot、保存再送、競合、no-op、最終問、旧循環、ADMIN、総サイズ拒否、ACK消失、bank CASを確認。B1のgroup形式、B2の受理後のサイズ増加、B3のroute間キー、B4の数値表記が不足。 |

## 検証

| 検証 | 結果 |
|---|---|
| Backend通常suite | **890 passed / 57 deselected**、117.97秒。`dynamodb`と`aws_e2e`を除外。 |
| `ruff check src skills tests --no-cache` | 成功。 |
| `git diff --check -- backend` | 成功。 |
| 指摘のローカル再現 | 11ケースで期待した現状の結果を確認。group 5、サイズ1、route間キー2、JSON数値3。 |
| Frontend側のZod数値判定 | `0`、`0.0`、`0e0`、`1.0`、`1e0`をすべて受理。 |

通常suiteの初回実行はWindows sandbox内でpytestのprivate一時領域にアクセスできず、fixture errorと終了時PermissionErrorで完走しなかった。
新しい検証用一時領域で、承認レビューを通った制限外実行により通常suiteを完走した。
既存のACL・失敗領域・過去証跡は変更していない。
suiteには検証用一時コピーのローカルTerraform試験が含まれるが、実AWSのsaved plan/applyは実行していない。

再現スクリプト: [backend_review_repro_20261007.py](../backend/.local/backend_review_repro_20261007.py)。
再現結果: [backend_review_repro_20261007.json](../backend/.local/backend_review_repro_20261007.json)。
再実行コマンドはbackendディレクトリで`.venv\Scripts\python.exe .local\backend_review_repro_20261007.py`。
再現スクリプトはsocket接続を禁止し、Memoryと固定snapshot clientのみを使用する。両ファイルはGit管理外。

今回作成した追跡対象の成果物は本レビュー記録のみ。実装の修正・commit・push・AWS再有効化・負荷試験は行っていない。
