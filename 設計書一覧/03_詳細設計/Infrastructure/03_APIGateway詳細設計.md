# API Gateway詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Type
HTTP API。

## 2. Authorizer
Cognito User Pool Access TokenをJWT Authorizerで検証。

## 3. CORS
Production Originを明示許可。
必要Header: Authorization / Content-Type / Idempotency-Key。
必要Methodのみ許可。

## 4. Throttling
回答受付・評価取得Routeを中心にRoute Throttling。
厳密なCost LimitはReserved Concurrency / OpenAI側制限も併用する。

## 5. Routeと認可

[採用済み6 Route](../../04_横断仕様/01_API契約一覧.md)を接続対象とする。
JWT subで本人データを検証し、ADMINはadmin-apiでGroupを再認可する。
回答受付は202、評価状態はGET。個別Lambda担当と非同期起動方式は次工程で確定する。
CORSは許可Originを明示し、上記Headerを含むPreflightと実リクエストを実API接続時に検証する。
