# Frontend単体MVP API契約

更新日: 2026-09-08。ユーザー承認済み実装計画v2に対応。

## 対象と正本

これはFrontend単体MVPが実Backendへ要求する契約です。旧BE01の `/v1/practices` とは互換ではありません。
Schemaの正本は [schemas/index.ts](../frontend/src/lib/api/schemas/index.ts)。MSWとAPI Clientが共用し、TypeScript型をZodから導出します。

Base URLは `NEXT_PUBLIC_API_BASE_URL`。Mockは `/api`。認証Headerの実装はBackend接続工程で追加します。
Request/ResponseはJSON、IDはUUID、日時はUTC ISO 8601です。質問番号は1始まりです。

## エンドポイント

| Method / Path | Request | Response |
|---|---|---|
| POST /sessions | category, difficulty="standard" | 201: sessionId |
| GET /sessions/:sessionId/question | なし | 200: sessionId, question, questionNumber, activeAttempt |
| POST /sessions/:sessionId/answers | questionId, answer | 202: attemptId, evaluationId, status |
| GET /evaluations/:evaluationId | なし | 200: evaluationId, attemptId, status; failedの場合error |
| GET /attempts/:attemptId/feedback | なし | 200: Feedback |
| POST /sessions/:sessionId/questions/next | fromAttemptId | 200: 更新後の質問取得Response |

Question: `id`, `category`, `difficulty`, `question`。
activeAttempt: 未送信はnull、それ以外は `attemptId`, `evaluationId`, `status`。
status: `processing | completed | failed`。

Feedback: `attemptId`, `sessionId`, `question`, `questionNumber`, `answer`, `score`, `summary`, `strengths`, `improvements`, 任意の `exampleAnswer`, `createdAt`。
Scoreは0〜100の整数。配列0件、回答例なしを許容します。HTMLとして描画しません。

カテゴリは `job_change`, `motivation`, `strengths`, `experience`, `difficulty`, `career`, `questions`。
回答は空白のみを禁止し、JavaScript文字列長で1〜2000。100〜300文字は推奨であり制限ではありません。

## エラー

形式は `{ "code": "VALIDATION_ERROR", "message": "..." }`。
画面はBackendのmessageを直接表示せず、既知codeを日本語に写像します。

| Status | code |
|---|---|
| 400 | VALIDATION_ERROR |
| 401 | UNAUTHORIZED |
| 404 | SESSION_NOT_FOUND / ATTEMPT_NOT_FOUND |
| 409 | SESSION_STATE_CONFLICT / IDEMPOTENCY_CONFLICT / EVALUATION_NOT_COMPLETED |
| 500 | INTERNAL_SERVER_ERROR |

評価失敗は評価GETの `status=failed` と `error` で通知します。通信異常と区別します。
Client内のcodeは NETWORK_ERROR / TIMEOUT / ABORTED / INVALID_RESPONSEです。

## 冪等性・競合

すべてのPOSTにUUIDの `Idempotency-Key` を必須とします。同一キー・同一路径・同一の検証済みPayloadは保存済みResponseを返します。内容が異なる場合は409です。
応答消失後の再送は同じキーとPayloadで行い、新しいAttemptを作りません。確定失敗後の再挑戦は新しいキーを発行します。
処理中に異なるキーで回答を送った場合は409。次問操作は現在のcompleted Attemptからのみ許可し、古い結果から巻き戻しません。GETは質問を進めません。
実Backendでは原子的なキー予約・結果保存が必要です。MSW StoreはFrontendテスト用で、本番の排他制御実装ではありません。

## 通信と復旧

- API Client: 15秒Timeout、呼び出し元AbortSignal、JSONとZod検証。
- 通常GET: 通信失敗・5xxだけ最大1回Retry。POST: 自動Retryなし。
- 評価: 2秒間隔。30秒で待機案内、120秒で自動確認停止。停止は評価失敗を意味しません。
- 非表示タブ・オフライン・終端状態・画面離脱時はポーリング停止。
- sessionStorageにバージョン付き下書き・未確定要求を保存。現在の質問と再挑戦コンテキストが一致するものだけ復元。
- Reload後はactiveAttemptで評価再開。未確定要求は同じキーで手動確認。保存不可なら画面内操作を継続し、復元不可の案内を表示。
- タブを閉じた後の保存は保証しません。

## Mock

7カテゴリ×3問、標準難易度。通常は3回目の評価取得で完了。固定Scoreと文章を返し、画面にサンプル評価と明示します。
開発者ツールで `sessionStorage.setItem('pocket:scenario', 'response_lost')` のように設定できます。
利用可能な値: success / slow / never / validation / unauthorized / not_found / server_error / network_error / response_lost / invalid_response / evaluation_failed / state_conflict。
回答送信のエラーシナリオは原則1回だけ発生します。再現し直す場合はタブのMock保存をリセットしてください。
Storyはparameters.mockで同じWorkerを起動でき、parameters.handlersで上書きできます。Nodeテストは同じHandlerとメモリRepositoryを使います。

## 実Backend接続の条件

本契約のエンドポイント、冪等性、評価状態に対応したBackendと認証方式が必要です。MSWを無効にしBase URLを設定しただけでは旧APIと接続できません。
認証トークンの付与、CORS、運用上の評価期限・保存期限・利用制限はFE-014で決定・実装し、同じE2Eシナリオを実Backendでも検証します。

参照: [MSW Browser integration](https://mswjs.io/docs/integrations/browser/)、[Next.js Static Exports](https://nextjs.org/docs/app/guides/static-exports)、[Storybook Next.js Vite](https://storybook.js.org/docs/get-started/frameworks/nextjs-vite)。
