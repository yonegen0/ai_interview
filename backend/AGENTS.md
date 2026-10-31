# Backend 開発規約

## 適用範囲と正本

- `backend/` に適用し、[ルート安全規約](../AGENTS.md)とAPI契約を優先する。
- Python 3.14系。`pyproject.toml`、`.python-version`、`uv.lock` を採用依存・ツール設定の正本とする。
- APIとFrontendの整合は [API契約](../docs/FRONTEND_API_CONTRACT.md) と `../contracts/` のfixtureを確認する。
- レイヤー変更や大規模リファクタを前提にせず、現在の実装への最小修正を選ぶ。

## Python・依存管理

- 既存命名（module/functionはsnake_case、classはPascalCase、定数はUPPER_SNAKE_CASE）に従う。
- 公開関数・境界・複雑な値に適切な型注釈を付ける。辞書の乱用を避け、既存Model/Pydanticを活用する。
- Pydanticの型・制約・バリデーションを、外部入力の信頼境界で適用する。
- 入力検証エラー・ドメインエラー・外部サービス障害・再試行可能エラーを意味的に分ける。
- 例外を無差別に握り潰さず、予期せぬ障害は秘匿情報なしで診断可能にする。
- メール・Token・回答本文・評価結果・Secrets・AWS認証情報を平文ログへ出さない。
- `ruff`の既存設定（`pyproject.toml`）に従い、無関係な書式変更を避ける。
- 開発環境は `uv sync --locked`、実行は `uv run --locked ...` を基本とする。
- 不要な依存・Runtime追加をしない。必要時だけ理由、脆弱性、lockfileへの影響を確認する。

## 責務分離（現在の構造に従う）

- `src/interview_backend/api/`：HTTP境界、JWT/認可、入力/応答の変換、エラー返却。
- `application/`：Session/Attempt/Evaluationなどのユースケース、処理順序、権限に依存しない業務制御。
- `models/`：既存ドメインモデル・状態・制約。意味のある不変条件を保持する。
- `repositories/`：データ永続化、DynamoDBの条件付き操作、抽象化された読書き。
- `evaluation/`：採点・AI Provider・Dispatcher/Worker/回復など、現在実装された責務を尊重する。
- `aws_runtime.py`・`aws_settings.py`等：AWS Runtime・設定・Handlerとの接続境界。
- 上記は既存コードの説明であり、名前だけを合わせるための新設レイヤーや移設を要求しない。
- コアロジックを直接AWS SDK・環境変数・HTTPレスポンス形式へ不必要に結合しない。

## API・認証・データ

- API契約、HTTP status、冪等キー、エラー形、ページング/復旧仕様を無断変更しない。
- ユーザー入力・パス・識別子・数値・文字数を外部境界で検証する。
- USER/ADMIN認可とToken署名・期限・issuer・audience等の既存検証を維持する。
- すべての本人別読書きで認証主体に紐づくPartition/Ownershipを検証する。
- Session・Attempt・Evaluationの関連、改訂番号、採点履歴、V1互換を保つ。
- DynamoDBのConditional Write、Version確認、必要なTransactionを維持し競合を検出する。
- 条件不一致を安易に上書き成功へ変換せず、業務上の競合とRetry可否を区別する。
- 一覧・参照・TTL・Retentionの変更では既存アクセスパターンと本人分離を監査する。
- 例外や再試行による評価重複・履歴破損・二重使用量計上を防ぐ。

## 非同期・Recovery

- 基本経路：DynamoDB Streams → Dispatcher → SQS → Worker。SchedulerによるRecoveryを保持する。
- イベント重複、順序乱れ、Lambda/SQSの再配送、部分失敗、Timeoutを前提に設計する。
- Condition/Lease/処理権と冪等キーで同一Attemptの重複処理を抑える。
- SQS可視性Timeout、DLQ、Batch部分失敗応答、再配送を現行構成と照合する。
- 評価中・完了・回復待機・失敗などの状態遷移を契約どおり維持する。
- リカバリを装う新規評価、二重推論/二重課金、無限Retryを追加しない。
- 外部障害は必要な証跡を保持して明示的に停止・回復可能にし、結果不明を成功扱いしない。

## AI Provider・評価契約

- 採用方針はAnthropic直接API Claude Haiku 5.5を本番標準、BedrockとOpenAIを明示設定の手動予備とする。
- AI Providerの採用方針と、現在の`main`への統合・AWS配備完了を混同しない。
- 自動フォールバックは設けず、明示切替・設定検証・権限確認・課金確認を維持する。
- FakeProviderは決定的なオフライン試験用。Fake成功を実モデルの品質・速度・IAM保証としない。
- 実モデル応答はSchema/構造・型・長さ・禁止値を検証し、無効出力を無検証で保存しない。
- Structured Output等の契約をProvider境界で保持し、生成内容の架空補完・越権を防ぐ。
- Coaching V2の30点評価・深掘り・文字数、STAR Ver.1.4の3案・入力保持・編集を壊さない。
- 回数/費用/利用量制限はサーバー側の原子的判定と監査可能な記録を優先する。
- Paid inference、実Claude、実Bedrock、実OpenAI試験は個別承認と費用/副作用の境界に従う。

## 品質・検証

- Unit：Pure Logic、Model、Status遷移、境界条件、例外系を確認する。
- Integration：Repository、DynamoDBインターフェース、非同期処理の組合せを確認する。
- Contract：Frontend Zod Schema、fixture、HTTP status、idempotency、V1互換を確認する。
- `uv run --locked ruff check .` と `uv run --locked pytest -q` を変更内容に応じて実施する。
- テストに既存の `dynamodb` / `aws_e2e` markerがあり、通常のpytest対象とは異なる点を守る。
- Mock/Fake/ローカルIntegrationと、実DynamoDB・実Bedrock・実AWS E2Eの検証結果を分ける。
- 実サービスに接続する検証はread-onlyを含め既存のRunbook/明示承認に従う。
- 既存成功試験の再利用はHEAD・lock・fixture・設定と実行条件が一致する場合に限る。
- セキュリティ・課金・互換性に関わる欠落を、期待値変更やskipで隠さない。

## 公式ドキュメント

- 対象Versionを固定して公式仕様を読み、セキュリティ・API変更は最新の公式更新も確認する。
- Python: https://docs.python.org/3.14/ ｜ Pydantic: https://docs.pydantic.dev/latest/
- uv: https://docs.astral.sh/uv/ ｜ Ruff: https://docs.astral.sh/ruff/
- boto3: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
- AWS Lambda: https://docs.aws.amazon.com/lambda/latest/dg/welcome.html
- DynamoDB: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html
- SQS: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html
- Bedrock: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html
- OpenAI（予備Provider）: https://developers.openai.com/api/docs/guides/structured-outputs
- Anthropic（標準Provider）: https://platform.claude.com/docs/en/api/messages ｜ https://platform.claude.com/docs/en/build-with-claude/structured-outputs ｜ https://platform.claude.com/docs/en/api/versioning
- 公式参照不可は未確認として記録。公式確認を口実に無関係な依存更新をしない。
