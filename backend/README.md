# Backend（P3実装完了・Python検証完了・実DB検証待ち）

2026-09-13のレビュー修正、通常344件・Frontend契約102件、実DB57件の収集結果は
[最新検証記録](../docs/P3_VERIFICATION.md)を参照。AWS試験は未実行で、P4には自動移行しません。

ユーザー指示によりP4のローカル実装を継続中です。P4完了ではありません。
[P4計画・Terraform手順](../docs/BACKEND_P4_PLAN.md)と
[P4検証記録・残作業](../docs/P4_VERIFICATION.md)を参照してください。
bootstrap State移行は`skills/p4/bootstrap_state.py`の専用実行口だけを使います。
初回閉鎖配備向けのinspect/replan、移行再開、manifest v2、CI保存planの検証を追加しています。
[初回実行・失敗再開手順](../docs/P4_TERRAFORM_RUNBOOK.md)を参照してください。
bootstrapは1台・1人で実行し、他hostから同時操作しません。AWS実行・移行成功の記録はまだありません。

Python 3.14・uv・Pydantic・boto3による、Memory/DynamoDB Repository＋Fake評価です。
HTTPサーバーではありません。Frontendは引き続きMSWを使用し、本Backendへ未接続です。
AWS・Docker・OpenAI Credentialなしで6 APIと業務遷移を検証できます。
初回の依存取得にはパッケージレジストリへの通信が必要です。

回答はFrontend・BackendともUTF-16単位で1〜500文字（100〜300文字推奨）へ統一しました。
本文は加工せず、通常の絵文字は2単位と数えます。選択・最新結果は[検証記録](../docs/BACKEND_P1_VERIFICATION.md)を参照。
旧501〜2000文字の未確定要求・Mock結果は移行対象外です。保存レコード全体が復元されない場合があります。
通常の長い下書きは保持し、送信前に500文字以下へ編集します。保存version・復旧手順は変更しません。

## セットアップと検証

Python 3.14とuvを準備し、リポジトリルートから実行します。uv検証版は0.11.8です。

```text
cd backend
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
uv run --locked interview-demo
```

共通fixtureをFrontendでも確認します（Node.js 22以上）。

```text
cd ../frontend
npm ci
npm run test:unit -- --run tests/backend-contract.test.ts
```

通常の変更ではuv.lockを更新しません。依存追加・更新時のみ明示的に更新します。
CIは[Backend workflow](../.github/workflows/backend.yml)で同じ確認を実行します。
GitHub上での実行・公開はこのローカル実装作業には含みません。

## APIと実行方法

契約の正本は[API契約](../docs/FRONTEND_API_CONTRACT.md)と
[Zod](../frontend/src/lib/api/schemas/index.ts)です。

| Method / Path | Request | Response |
|---|---|---|
| POST /sessions | category, difficulty="standard" | 201・sessionId |
| GET /sessions/:sessionId/question | なし | 200・SessionResponse |
| POST /sessions/:sessionId/answers | questionId, answer | 202・attemptId, evaluationId, status |
| GET /evaluations/:evaluationId | なし | 200・processing / completed / failed |
| GET /attempts/:attemptId/feedback | なし | 200・Feedback |
| POST /sessions/:sessionId/questions/next | fromAttemptId | 200・更新後SessionResponse |

`build_runtime()`で組み立てた同じruntimeを全呼出しで使います。
`runtime.handler(event)`はHTTP API v2形式のイベントとJSON文字列bodyを受け、
statusCode、Content-Type、JSON文字列bodyを返します。base64 bodyとヘッダー大小文字に対応します。
`demo_event()`はローカル専用イベントfixture作成用です。

本人は`requestContext.authorizer.jwt.claims.sub`のみから取得します。
AuthorizationヘッダーのToken署名検証は行いません。
任意のsubを渡せるローカルHandlerを、そのまま公開してはいけません。
P4で信頼できるJWT Authorizer経由のイベントに制限します。
存在しない／他人のSessionはSESSION_NOT_FOUND、Attempt／EvaluationはATTEMPT_NOT_FOUND。
未知RouteのみNOT_FOUND（404）、既知Pathの非対応MethodはMETHOD_NOT_ALLOWED（405）です。
405には対応MethodのAllowヘッダーを付けます。主体欠落の401を先に判定します。
scoreは有限の整数値（78.0・7.8e1も含む）を受理し整数で返します。bool・文字列・小数・非有限値は拒否します。
不正入力400、主体欠落401、業務競合409、内部例外500は固定messageです。

## 保存・冪等性・評価

- 全POSTにUUIDのIdempotency-Key。owner＋keyを識別子とし、Method・Path・検証済みPayloadを比較。
- 未知Payload項目を除去し、JSONキー順だけの違いは無視。回答の空白・改行は保持。
- 保存済み要求の照合は現在の業務状態検証より先。成功時の元HTTP Status・bodyを再返却。
- 同一キーの操作先／本文違いは409。400・401・404・409は成功記録に保存しない。
- Session、Attempt、Evaluation、Dispatch、冪等応答の5件を原子的に受付。Memoryはcopy-on-write、DynamoDBは条件付きTransaction。
- 読み出し値は保存状態から切り離す。全データをコピーするため、小規模ローカル検証専用。
- 21問はMSWのUUID・カテゴリ・本文を継承。Session作成時に質問順・本文をスナップショット。
- カテゴリ先頭から固定順に巡回。questionNumberは増加、再挑戦は同じ質問。
- 回答受付はprocessingで202を返す。`runtime.dispatcher.dispatch(owner, evaluationId, generation)`が配送し、`runtime.worker.run(owner, evaluationId, generation)`が評価する。
- GETを何回呼んでも評価は進まない。レスポンス後の暗黙継続・バックグラウンドThreadはない。
- Worker内部はpending / running / terminal。実行中・終端の重複起動はProviderを呼ばない。
- 正常出力を検証し、BackendがID・質問・回答・UTC日時を組み立てる。
- Fake例外／不正出力はfailed＋EVALUATION_FAILED。Providerを自動再呼出しせず、保存だけを上限付き再試行する。
- Recoveryは未開始Workerだけ再投入し、開始後の結果喪失はOUTCOME_UNKNOWNで終端化する。`runtime.recovery.tick()`で明示実行する。
- 評価確定は対応するactiveAttemptのみ更新。古いWorkerで新しい操作段階を上書きしない。
- Fakeの結果は品質評価ではない。Promptはカテゴリ基準・正式質問と回答データを別フィールドで保持。
- 通常ログは操作・ID・statusだけ。回答、Prompt、評価本文、Token、例外本文を出力しない。

## 構成

| 配置 | 責務 |
|---|---|
| src/interview_backend/api | イベント解析・Route・固定HTTPエラー |
| application | 公開入力検証・fingerprint・6操作 |
| models | Zod対応公開モデル・非公開記録 |
| repositories | 共通業務操作、Memory、DynamoDB、JSON/rev/GSI、保存予算 |
| evaluation | Prompt・Fake・Worker・Dispatcher・Recovery・内部イベントadapter |
| assets | 21問JSON・ロード時検証 |
| bootstrap.py / demo.py | 明示DIと同一プロセスの実行例 |
| tests/unit / integration / contracts / dynamodb | 業務・SDK Stub・HTTP・共通契約・P4実DB試験 |

共通fixtureは[contracts/backend-fixtures.json](../contracts/backend-fixtures.json)。
Pythonでは実Handler応答との一致とモデル受理、Frontendでは既存Zodの受理とMSW質問一致を確認します。

## 保証しない事項と次工程

Memoryはプロセス終了で全データを失い、本番永続化を保証しません。
DynamoDB実装の原子性・競合・永続化、実Streams/SQS/Scheduler/IAMはP4検証待ちです。
通常pytestはdynamodbマーカーを除外します。明示的なAWS dev設定で `pytest -m dynamodb` を実行すると
run専用Tableを作成し、そのTableだけを後片付けします。設定不足・疎通失敗は失敗です。
[P3検証記録とP4手順](../docs/P3_VERIFICATION.md)、[環境選定](../docs/P3_ENVIRONMENT.md)を参照してください。

`build_runtime(mode="aws", region="...", table="...")`は既存Tableへの明示接続です。
起動時にTableを作成しません。既定はMemoryで、CLIにはAWS自動接続がありません。
ProviderとPublisherの既定はFake。実Provider、JWT署名、ユーザー管理、履歴等は後続工程です。

実装時の確認資料：
[Pydantic Strict Mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)、
[uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)。
