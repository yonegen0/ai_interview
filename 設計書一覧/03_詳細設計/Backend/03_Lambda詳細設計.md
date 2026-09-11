# Lambda詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 責務境界

- practice-api: Question Bank、Sessionを含む練習管理。Profile／History／Favoriteは将来機能。
- evaluation-api: AI評価・出力検証・評価結果保存。OpenAIへアクセス可能な唯一のLambda責務。
- admin-api: ADMIN再認可後のUser一覧・詳細・管理操作。

3責務の方針を維持する。6 Routeの個別担当、受付と実行の分割・起動権限は非同期方式と合わせて次工程で確定する。

## 2. 外部から必要な処理順

1. JWT主体とRequestを検証する。
2. 所有者・現在の質問・状態を検証し、Question Bankの正式本文を取得する。
3. 冪等要求とAttempt／Evaluationの関連を永続化する。
4. 回答POSTへ202とattemptId／evaluationId／statusを返す。
5. BackendでPrompt構築、AI呼出、Pydantic検証を行い結果または失敗を保存する。
6. FrontendのGETには保存済み状態・結果を返す。

これは外部契約を示す順序であり、同じLambdaがレスポンス返却後も継続する実装を意味しない。
GET回数で完了するMSW処理はテスト専用。
起動方式、保存と起動の整合、起動漏れ・重複・期限切れ回復は
[Backend着手前の必須事項](../../04_横断仕様/06_決定事項_未確定事項.md)。

## 3. Dependency・ログ

openai／pydantic／aws-lambda-powertools／boto3を候補とし、Runtime互換性を実装前に確認する。
本文・Token・PIIをログへ出さない。評価処理滞留と失敗を検出できるメタデータを扱う。
