# Backend基本設計書

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Runtime
AWS Lambda + Python 3.14をMVP第一候補とする。
実装時にOpenAI SDK / Pydantic / Powertools等の互換性を公式確認する。

## 2. Lambda分割
### practice-api
Question Bank / Sessionを含む練習管理。履歴 / お気に入り / User Profileは将来機能。

### evaluation-api
AI評価 / Structured Output / Idempotency / OpenAI Usage / 保存。
OpenAIへアクセス可能な唯一のLambda。

### admin-api
求職者一覧 / 詳細 / 管理操作 / Cognito Admin API。
ADMIN Group再検証を行う。

## 3. Network
ユーザーVPCへ入れない。NAT Gatewayは使用しない。

## 4. Validation
Frontend Zod + Backend Pydanticの二重Validation。

## 5. AI抽象化
`InterviewEvaluator -> LLMProvider -> OpenAIProvider`。
MVPではこれ以上の過剰抽象化をしない。

## 6. 採用契約と実装着手条件

[6 RouteのAPI契約](../../docs/FRONTEND_API_CONTRACT.md)を採用する。回答は永続化して202受付、評価状態とFeedbackはGET。
全POSTのIdempotency-Key、Backend生成リソースID、100点評価と指摘配列を使用する。
非同期起動、受付と起動の整合、重複・期限切れ回復、個別Route担当とIAMは
[着手前の必須事項](../04_横断仕様/06_決定事項_未確定事項.md)で確定する。3責務の方針は維持する。
