# API契約一覧

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 正本

型・制約は[Zod Schema](../../frontend/src/lib/api/schemas/index.ts)、HTTP・冪等性・復旧は
[Frontend API契約](../../docs/FRONTEND_API_CONTRACT.md)、採用判断は[ADR-002](../../docs/ADR-002-frontend-contract-alignment.md)を参照する。
以下は採用済み6エンドポイントの索引。認証・Backendは未実装であり、Base URL変更だけでは接続完了にならない。

| Method / Path | Request | 成功時Response |
|---|---|---|
| POST /sessions | category, difficulty="standard" | 201: sessionId |
| GET /sessions/:sessionId/question | なし | 200: sessionId, question, questionNumber, activeAttempt |
| POST /sessions/:sessionId/answers | questionId, answer | 202: attemptId, evaluationId, status |
| GET /evaluations/:evaluationId | なし | 200: evaluationId, attemptId, status; failedの場合error |
| GET /attempts/:attemptId/feedback | なし | 200: Feedback |
| POST /sessions/:sessionId/questions/next | fromAttemptId | 200: 更新後の質問取得Response |

## 共通条件

- 質問IDを含むIDはUUID。全POSTでFrontend生成Idempotency-Keyを送る。
- sessionId／attemptId／evaluationIdはBackend生成。状態はprocessing／completed／failed。
- Feedbackはscore（0〜100整数）、summary、strengths、improvements、任意exampleAnswerと管理情報。詳細は正本を参照。
- 回答はJavaScript文字列長で1〜2000、空白のみ禁止。100〜300文字は推奨。
- カテゴリは現行7カテゴリを維持。カテゴリ取得APIは追加しない。
- Error Bodyは{ code, message }。HTTPとコードの対応は[エラー一覧](04_エラーコード一覧.md)。
- GETで質問や評価処理を進めない。次問POSTは現在のcompleted Attemptからのみ受け付ける。

## 次工程

上記以外の履歴・お気に入り・Profile・Admin Route、Pagination、Filterは未確定。
全Routeが未確定という意味ではない。実行方式・物理設計は[必須事項](06_決定事項_未確定事項.md)を参照。
