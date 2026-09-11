# DynamoDBインフラ詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Table
1 Table / On-Demand。

## 2. Protection
PITR、encryption、deletion protection等はdev/prodで要否を整理する。

## 3. GSI
Session／Attempt／Evaluation／冪等要求の本人取得、および将来のAdmin一覧・History・FavoriteのAccess Patternから必要最小限で決定。
[論理モデル](../../04_横断仕様/02_データモデル一覧.md)は物理Item数を固定しない。物理キー・Transactionと合わせて着手前に確定する。

## 4. TTL
Retention方針決定後に追加。
