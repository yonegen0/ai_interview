# API詳細設計

> 文書バージョン: 2.3\
> 更新日: 2026-09-12
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 正本・採用Route

[横断API一覧](../../04_横断仕様/01_API契約一覧.md)は6 Routeの索引。
HTTP・冪等性・復旧は[API契約](../../../docs/FRONTEND_API_CONTRACT.md)、
型・制約は[Zod Schema](../../../frontend/src/lib/api/schemas/index.ts)を正本とする。
本書では重複したRequest／Response型を定義しない。

## 2. 認証・入力

全保護RouteにJWT Authorizerを使用し、主体はJWT subから取得する。
Session／Attempt／Evaluationを取得する際に所有者を検証する。
質問IDを含むIDはUUID。正式な質問本文はBackendのQuestion Bankを正とする。
回答はJavaScript文字列長で1〜500、空白のみは禁止。Pydantic側との互換を検証する。
UTF-16単位で数え、本文は加工しない。scoreは有限の整数値78.0・7.8e1も受理し、整数として返す。
bool・文字列・小数・非有限値・範囲外を拒否し、他のフィールドのStrict設定は維持する。
P1ローカルHandlerは主体欠落を401、未知Routeを404とする。既知Pathの未対応Methodは405・METHOD_NOT_ALLOWEDと対応MethodのAllowヘッダーを返す。
カテゴリは現行7種類。カテゴリ取得Routeは追加しない。

## 3. 受付と評価

回答POSTは現在のSession・質問・処理状態と冪等キーを検証し、
要求とAttempt／Evaluationの関連を永続化して202を返す。
Backendは評価を継続し、GETでprocessing／completed／failedを取得できるようにする。
failedはHTTP 200とerrorで通知する。HTTPエラーは[エラー一覧](../../04_横断仕様/04_エラーコード一覧.md)。
Feedbackは0〜100 score、summary、strengths、improvements、任意exampleAnswerと正本の管理項目。
質問GETは質問を進めず、評価GETもAI処理を進める契機にしない。

## 4. 競合と将来Route

処理中に別キーで回答を送る場合や、現在の質問と不一致の場合は409。
次問POSTは現在のcompleted Attemptからのみ許可し、過去の結果から巻き戻さない。
Profile／履歴／お気に入り／Admin Route、Pagination、Filterは未確定。
各RouteのLambda担当と非同期起動方式は[着手前の必須事項](../../04_横断仕様/06_決定事項_未確定事項.md)で確定する。
