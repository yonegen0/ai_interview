# DynamoDB詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. Capacity・論理責務

On-Demand、1 Tableを維持する。
[論理モデル一覧](../../04_横断仕様/02_データモデル一覧.md)のUserProfile／Session／Attempt／Evaluation／冪等要求記録を扱う。
1論理モデルを必ず1 Itemへ分けるとは限らない。v2.0のProfile／Evaluationのキー例は物理設計の確定値としない。

## 2. 必須Access Pattern

- JWT sub本人のProfile取得。
- sessionIdから所有者・現在の質問・activeAttemptを取得。
- evaluationIdから所有者・attemptId・評価状態・失敗情報を取得。
- attemptIdから所有者・Session・質問・回答・Feedbackを取得。
- ユーザーとIdempotency-Keyから要求識別情報と保存済みHTTP応答を取得。
- 現在のcompleted Attemptから次問を更新し、過去の結果による巻き戻しを拒否。
- 将来機能として履歴の新しい順取得、お気に入り取得、Admin User一覧・詳細。

## 3. 整合性

SessionとAttempt／Evaluationの関連、冪等キー予約と受付応答保存を整合させる。
同一要求の再送・処理再実行でAttempt／Evaluationを増やさず、Profile集計を二重加算しない。
評価完了後のFeedbackとactiveAttemptの状態が矛盾しないようにする。
条件付き更新・Transaction・キー・GSIは[必須事項](../../04_横断仕様/06_決定事項_未確定事項.md)で確定する。
外部AI呼出とDB更新を単一Transactionで原子化できる前提を置かない。

## 4. Profile・保存

name／email／status、totalPracticeCount／favoriteCount、lastPracticeAt、
currentWeekKey／currentWeekPracticeCount、createdAt／updatedAtの非正規化方針を維持する。
保存期間・冪等記録保持期間は未確定。TTLは即時削除用途に使わない。
退会等の即時削除は明示Deleteを設計する。
