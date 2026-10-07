# Backendレビュー指摘の修正

2026-10-07。[未コミット差分のレビュー](BACKEND_UNCOMMITTED_REVIEW_20261007.md)のB1〜B4を修正した。
既存の未コミット変更を保持し、commit・push・AWS配備は行っていない。

## 修正内容

| 指摘 | 修正と回帰確認 |
|---|---|
| B1: ADMIN groupの形式 | 配列・JSON配列・既存カンマ区切りに加え、`[ADMIN]`・`[USER ADMIN]`・`[USER, ADMIN]`を正規化する。ADMINとの完全一致を維持し、ADMIN_HELPER・NOTADMIN・小文字・壊れた配列・異なる型を拒否する。 |
| B2: 回答受付後のサイズ超過 | Sessionの保存上限350KiBから更新用に1KiBを確保する。新規公開・変更のない保存・新規練習開始を検査し、余裕のない一覧を400 QUESTION_BANK_TOO_LARGEで拒否する。受理した上限付近の一覧で回答・評価・再挑戦・次問とDynamoDB書込みの組立てを確認する。修正前に公開された一覧も新しい練習開始時に検査する。 |
| B3: API間の冪等キー | 専用の管理保存記録と既存の成功応答記録を保持し、双方で相手の記録がないことを同じトランザクションの条件に含める。開始・回答・次問と管理保存の両方向を409とし、成功済み再送・別利用者の同じキーは保持する。Memoryの同時実行とDynamoDBの競合再読取りを確認する。 |
| B4: JSONの整数表記 | 有限な整数値のfloatだけをintへ変換してからexpectedVersionを検証する。整数・小数点・指数表記を同じ版・fingerprintとして扱い、bool・文字列・小数・非有限値・範囲外を拒否する。共通JSON corpus 16件をBackend PydanticとFrontend Zodの両方で検証する。 |

B3では新しい共通予約レコードを作らず、既存の2種類の記録への条件付き存在確認を使う。
一般APIは質問管理記録を読み、管理APIは利用者partitionのPK・SKのみをProjectionExpressionで読む。
管理APIが存在しないと判断した既存成功記録もConditionCheckに含めるため、読取り後に競合要求が成功しても両方がcommitすることはない。
既存の成功済み応答は相手の存在確認より先に返す。保存形式の移行は不要。

Terraformのadmin Roleに、PK・SKの投影取得とトランザクション内の存在確認だけを追加した。
`dynamodb:Attributes`、`dynamodb:Select`、`dynamodb:ReturnValues`を制限し、利用者partitionへのPutItemを許可しない。
条件の設計は[AWSの属性単位アクセス制御](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html)に基づく。
manifest v3の完全比較とTerraform mock testも更新し、本文取得への拡大・投影条件の除去・ALL_OLD・利用者データ書込みを拒否する試験を追加した。
実IAMの許可・拒否は今回AWSへ接続して検証していない。

## 主な変更先

- [認可groupの処理](../backend/src/interview_backend/api/admin.py)
- [request型](../backend/src/interview_backend/models/public.py)
- [ドメイン処理](../backend/src/interview_backend/repositories/domain.py)、[サイズ検査](../backend/src/interview_backend/repositories/codec.py)
- [DynamoDBの投影取得](../backend/src/interview_backend/repositories/dynamodb.py)、[Memoryの存在確認](../backend/src/interview_backend/repositories/memory.py)
- [admin IAM](../terraform/modules/service/iam.tf)、[manifest読戻し](../backend/skills/p4/manifest_checks.py)
- [サイズ・API間競合の回帰試験](../backend/tests/unit/test_backend_review_fixes.py)
- [共通の版番号fixture](../contracts/question-bank-version-fixtures.json)、[Backend契約試験](../backend/tests/contracts/test_contract.py)、[Frontend契約試験](../frontend/tests/question-management.test.ts)

## 検証

| 検証 | 最終結果 |
|---|---|
| Backend通常suite | **940 passed / 57 deselected**、96.48秒。実DynamoDB・aws_e2eを除外。修正前890件から回帰50件を追加。 |
| サイズ・API間競合の回帰試験 | 17 passed。未公開拒否、修正前の一覧からの開始拒否、受理後の進行、両方向の競合、再送、別owner、同時実行を含む。 |
| Frontendの質問管理・共有契約 | 23 passed。共通版番号corpus 16件を含む。 |
| Backend Ruff | 成功。 |
| Frontend ESLint（変更した契約試験） | 成功。 |
| Frontend TypeScript `tsc --noEmit --incremental false` | 成功。 |
| Terraform fmt | 変更したIAMと契約試験で成功。 |
| Terraform offline validate | bootstrap／dev／test／serviceの4構成で成功。 |
| Terraform mock test | service 34 passed、bootstrap 1 passed。 |
| `git diff --check` | 成功。 |

通常suiteは前回確認したWindowsのprivate一時領域制限を避け、承認レビューを通った制限外実行で検証した。
Frontendはsandbox内の子プロセス起動拒否後、制限外実行で同じ契約試験を成功させた。
Terraformは認証情報・実tfvars・State・既存`.terraform`を除外した新しいコピーで実行し、
既存providerのローカルmirrorのみを使った。AWSやprovider registryへ接続していない。
初回コピーはdevの固定provider 6.65.0がmirrorにないため停止し、各構成の既存cacheを列挙した新しいコピーで完了した。
コピーと元のlockfileの一致、および元Terraformファイルのhash不変を確認した。
元の失敗領域・過去証跡・ACLは変更していない。

Terraformログ: [validation.log](../.p4-artifacts/backend-review-fixes-terraform-02/validation.log)（Git管理外）。

## 配備と残る確認

コード・Terraform定義の修正まで完了。実AWSへのsaved plan・apply・再有効化・OTP送信・負荷試験は行っていない。
既存devの閉鎖状態を変更せず、既存のAPI p95 Gate FAILを変更していない。
新しいPOSTでは記録の存在確認の強整合読取りとConditionCheckが増えるため、実配備後の性能確認は別工程となる。
実JWTでのADMIN認可とIAM条件の実効許可・拒否も、明示的に承認された実接続試験で確認する必要がある。
過去の再現結果は保持し、修正後の動作は回帰テストで確認した。
