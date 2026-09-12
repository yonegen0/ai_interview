# APIクライアント・Validation詳細設計

> 文書バージョン: 2.3\
> 更新日: 2026-09-12
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 正本・Request

[API契約](../../../docs/FRONTEND_API_CONTRACT.md)と
[Zod Schema](../../../frontend/src/lib/api/schemas/index.ts)を参照。
全POSTにFrontend生成Idempotency-Keyを付与する。回答POSTのbodyはquestionIdとanswer。
IDはUUID。sessionId／attemptId／evaluationIdはBackendが生成する。
Authorization Bearer Access Token付与・更新は次の認証工程で実装する。

## 2. Response・入力検証

JSONをZodでRuntime Validationする。Schema mismatchはINVALID_RESPONSEとし、
通常の業務Errorと分離する。Production Logへ本文全体を出さない。
回答はJavaScript文字列長（UTF-16 code unit）で1〜500、空白のみは禁止。
上限定数ANSWER_MAX_LENGTHと明示的なvalue.length検証を用い、入力・POST・Feedbackのanswerに共通適用する。
trimは空白判定だけに用い、本文の加工・正規化・切り詰めは行わない。通常下書きは長くても保存・復元する。
旧501〜2000文字pendingは保存検証でレコード全体が破棄され得る。互換Schemaや保存version変更は追加しない。
Python側でもこの長さの定義との互換を検証する。100〜300文字は推奨であり制限ではない。

## 3. 通信・再確認

API Clientは15秒Timeoutと呼出元AbortSignalを扱う。
通常GETは通信失敗・5xxだけ最大1回Retry。評価GETは自動Retryなし。
全Mutationは自動Retryなし。5xx・応答消失など受付不明時は同じキーとPayloadで手動確認する。
FORBIDDEN／RATE_LIMITEDも自動再送しない。429の待機タイマーは追加しない。
再挑戦は確定失敗後に新しいキーを生成する。

## 4. Error表示

[エラー一覧](../../04_横断仕様/04_エラーコード一覧.md)に従って既知codeを日本語へ写像する。
追加はFORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERROR。
未知codeは汎用表示。Backendのmessageを直接表示しない。
HTTP 200の評価GETでstatus=failedの場合は既存の評価失敗画面へ進む。
HTTP 502/504の通信エラーから評価自体の失敗を決めつけない。
