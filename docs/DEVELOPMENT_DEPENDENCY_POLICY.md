# 工程と依存追加の判断方針

状態: 採用。ユーザー指示に基づく開発・設計・コード生成の共通方針。

## 現在地

P0・P1完了、P2-201〜212は設計確定。P3はユーザー指示により実装し、実DB検証待ち。
P3の[環境選定](P3_ENVIRONMENT.md)はPython中心・実DBをP4へ送る方針。[実装記録](P3_VERIFICATION.md)を参照。
設計レビューと文書検証は[P2確認記録](p2/P2_VERIFICATION.md)。実装・実機保証とは区別する。
P2完了後のP3開始指示は受領済み。後続AWS環境作業はP4で扱う。
先行した草案や未検証コードが存在しても工程完了の証拠にはしない。

## 依存を追加する前の確認

1. 現在の工程で本当に必要か。
2. 既存環境・既存ライブラリで代替できないか。
3. Production依存か、開発補助依存か。
4. 今追加しないと現在の作業を進められないか。
5. 将来必要かもしれない、便利だからという理由だけになっていないか。
6. 更新・脆弱性対応・セットアップ・削除を含む保守コストが妥当か。

現在工程に不要なら導入せずスキップする。不足ツールを見つけても別Runtimeを自動導入しない。
必要な場合は既存環境を優先し、追加依存を最小化し、Project Localで管理する。
Runtime・Package Manager・Docker・Java・グローバルpackage・恒久環境変数・PATH・
OS設定・常駐Serviceの変更は、現在の必要性と影響を説明してから扱う。
導入直前に必要な外部仕様を最新公式資料で確認する。将来の導入のために現在の環境を変更しない。

## P2の境界

P2は設計工程。Entity、状態遷移、Access Pattern、Transaction、Recovery、Concurrency、
Retry、Security、Retentionを文書で検討・確定する。
Docker/Desktop、Java/JRE/JDK、Portable Java、DynamoDB Local、起動環境、追加CLI、
Runtime移行、P3向け依存追加、Repository本実装、AWS dev構築を実施しない。
既存Frontend・Backend・Memory・Fake ProviderとP2-201を作り直さない。

Backend基本方針はPython 3.14、uv、Pydantic、pytest、Ruff、AWS SDK。
各導入・更新は必要な工程で実施する。Javaを選んでもBackend本体の依存と扱わず、
DynamoDB Local直接起動方式の開発補助Runtimeとして記録する。

## P3-302 DynamoDB検証環境選定

P3開始時にPC環境と必要な試験を確認して選ぶ。DynamoDB Localは前提条件にしない。

| 既存環境・意向 | 候補 |
|---|---|
| Dockerが存在 | Docker版DynamoDB Local |
| Javaが存在 | Javaで直接起動するDynamoDB Local |
| 両方なし | Local専用Runtime追加の必要性とAWS dev案を比較 |
| ローカルRuntimeを増やさない | P4のAWS dev DynamoDB |
| 上記以外 | AWS公式に沿い、必要な試験を満たす方法を比較 |

選定理由、追加依存、費用、認証、試験データ、起動・停止・後片付けを記録する。
選定後、必要な場合だけ構築する。AWS案の選択自体はAWS操作の実行許可ではない。
既存ZIPがあることも、その展開や実行を選ぶ理由にはしない。

P3の実装完了と、選定環境での永続化・Transaction・競合検証完了を別に記録する。
AWS試験をP4へ送る場合は「P3実装完了・実機検証待ち」とし、無条件にP3全体完了としない。
Mock/Stubだけで実DynamoDBの保証を満たしたとは扱わない。

## 中断時の先行変更記録

2026-09-12の前作業ではPython 3.14.4取得、Backend仮想環境再作成、boto3を含む同期、
pyproject/lock/Python指定/Ruff設定/CI変更、内部モデルのDispatch/lease属性追加が行われた。
Java ZIP（202,320,866 bytes）とDynamoDB Local ZIP（56,623,311 bytes）は
`backend/.local`へダウンロード済み。取得処理は終了し、展開・Java配置・Local起動は未実施。
これらは未検証の先行変更で、P2に必要な作業やP3完了実績ではない。

先行したbackend/.gitignoreの変更では従来のcache等のignore項目も置換されている。
現状を記録し、今回の文書修正ではコード・設定の巻き戻し、削除、アンインストールを行わない。
P1の184件成功は当時の検証記録であり、この先行変更後の成功を意味しない。

今回の実施対象は方針・計画・P2-202〜212設計文書と引継ぎ資料だけ。以前の「Planモードで未編集」は
前ターン時点の記録であり、本方針の反映後も未編集であるという意味ではない。
