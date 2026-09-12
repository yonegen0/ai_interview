# ローカルBackend（P1）

Python 3.13・uv・Pydanticによる、単一プロセスのメモリRepository＋Fake評価です。
HTTPサーバーではありません。Frontendは引き続きMSWを使用し、本Backendへ未接続です。
AWS・Docker・OpenAI Credentialなしで6 APIと業務遷移を検証できます。
初回の依存取得にはパッケージレジストリへの通信が必要です。

回答はFrontend・BackendともUTF-16単位で1〜500文字（100〜300文字推奨）へ統一しました。
本文は加工せず、通常の絵文字は2単位と数えます。選択・最新結果は[検証記録](../docs/BACKEND_P1_VERIFICATION.md)を参照。
旧501〜2000文字の未確定要求・Mock結果は移行対象外です。保存レコード全体が復元されない場合があります。
通常の長い下書きは保持し、送信前に500文字以下へ編集します。保存version・復旧手順は変更しません。

## セットアップと検証

Python 3.13とuvを準備し、リポジトリルートから実行します。uv検証版は0.11.8です。

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
- Session、Attempt、Evaluation、冪等応答をコピー上で準備し、単一プロセスのロック内で一括反映。
- 読み出し値は保存状態から切り離す。全データをコピーするため、小規模ローカル検証専用。
- 21問はMSWのUUID・カテゴリ・本文を継承。Session作成時に質問順・本文をスナップショット。
- カテゴリ先頭から固定順に巡回。questionNumberは増加、再挑戦は同じ質問。
- 回答受付はprocessingで202を返す。評価の開始は`runtime.worker.run(evaluationId)`を明示実行。
- GETを何回呼んでも評価は進まない。レスポンス後の暗黙継続・バックグラウンドThreadはない。
- Worker内部はpending / running / terminal。実行中・終端の重複起動はProviderを呼ばない。
- 正常出力を検証し、BackendがID・質問・回答・UTC日時を組み立てる。
- Fake例外／不正出力はfailed＋EVALUATION_FAILED。生の例外・不正出力を保存しない。自動Retryなし。
- 評価確定は対応するactiveAttemptのみ更新。古いWorkerで新しい操作段階を上書きしない。
- Fakeの結果は品質評価ではない。Promptはカテゴリ基準・正式質問と回答データを別フィールドで保持。
- 通常ログは操作・ID・statusだけ。回答、Prompt、評価本文、Token、例外本文を出力しない。

## 構成

| 配置 | 責務 |
|---|---|
| src/interview_backend/api | イベント解析・Route・固定HTTPエラー |
| application | 公開入力検証・fingerprint・6操作 |
| models | Zod対応公開モデル・非公開記録 |
| repositories | 原子的操作のProtocolとメモリ実装 |
| evaluation | 構造化Prompt・Provider境界・Fake・明示Worker |
| assets | 21問JSON・ロード時検証 |
| bootstrap.py / demo.py | 明示DIと同一プロセスの実行例 |
| tests/unit / integration / contracts | 業務・HTTP・共通fixture検証 |

共通fixtureは[contracts/backend-fixtures.json](../contracts/backend-fixtures.json)。
Pythonでは実Handler応答との一致とモデル受理、Frontendでは既存Zodの受理とMSW質問一致を確認します。

## 保証しない事項と次工程

プロセス終了で全データを失います。複数プロセスの排他、永続化、起動漏れ、
Worker強制終了後の回復、ロック期限、Cognito署名検証、OpenAI品質・Timeout・課金、
DynamoDB Transaction、ユーザー管理・集計・履歴・お気に入り・管理画面は未実装です。
特にWorkerがclaim後に停止するとrunningのままです。P1で自動再実行しません。
本番のメモリ利用や、複数Lambdaへのそのままの配備は認められません。

次は[実装計画](../AI面接練習Webアプリ｜実装計画.md)のP2です。
[ADR-003](../docs/ADR-003-local-backend-foundation.md)、
[必須決定事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)、
[検証記録](../docs/BACKEND_P1_VERIFICATION.md)を参照してください。

実装時の確認資料：
[Pydantic Strict Mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)、
[uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)。
