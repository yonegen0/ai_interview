# Error・Retry・Timeout詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. FrontendとBackendの期限を分離する

| 対象 | 採用値・状態 |
|---|---|
| Frontendの1リクエストTimeout | 15秒 |
| 評価状態のGET間隔 | 2秒 |
| 長時間待機案内 | 30秒 |
| Frontendの自動確認停止 | 120秒。失敗・キャンセルを意味しない |
| Backendの処理期限・ロック期限 | 非同期実行方式と合わせて次工程で決定 |

v2.0のLambda約25秒／OpenAI約8秒・Retry最大1回は同期処理前提の暫定案。
非同期Backendの確定値に転用しない。回答受付はAI完了を待たず永続化後に202を返す。

## 2. Frontend Retry・復旧

全POSTは自動Retryなし。通常GETはNETWORK_ERRORまたは5xxだけ最大1回、評価GETは自動Retryなし。
403/429でも自動再送しない。5xx・Timeout・応答消失等の受付不明POSTは同じキーとPayloadで手動確認する。
確定失敗後の再挑戦は新しいキー・Attempt。

## 3. Backendの外部呼出Retry候補

429／5xx／Network Timeoutを検討対象とし、回数・期限・Exponential Backoff＋Jitterは次工程で確定する。
Request Validation、認証認可、恒常的な出力Validation不正は原則Retryしない。
外部AI呼出の応答消失時は完了不明・二重課金の可能性があるため、無条件再実行しない。
冪等キーだけで外部呼出のexactly-onceが保証されるとは扱わない。

## 4. Error通知

HTTP Statusとコードは[エラー一覧](../../04_横断仕様/04_エラーコード一覧.md)。
評価自体の失敗はHTTP 200の評価GETでstatus=failedとerrorを返す。
HTTP 502/504は通信リクエストの失敗であり、評価失敗とは分離する。
BackendのmessageをFrontendへ直接表示しない。
