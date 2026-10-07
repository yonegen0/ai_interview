# Frontend単体MVP API契約

## 2026-10-06 質問管理・通し練習の現行契約

以下を現行契約とする。後段の2026-09-12記述は既存6 APIと旧データ互換の基礎仕様として残す。
質問本文・順番の原本はBackendの質問JSON、型・制約はFrontend ZodとBackend Pydanticで照合する。

### 練習開始と終了

`POST /sessions`は`{mode:"full",difficulty:"standard"}`、または
`{mode:"category",category:<有効カテゴリ>,difficulty:"standard"}`を受け付ける。
fullのcategory指定は禁止。categoryモードはcategory必須。既存のmode省略形式も受理し、
新規カテゴリ練習として扱う。旧要求のfingerprintへmodeを追加しない。
成功応答201のsessionIdは維持する。

`GET /practice-options`はログイン必須で、`bankVersion`、`totalQuestions`、
`categories:[{id,label,questionCount}]`を返す。質問のないカテゴリを省き、本文・更新者は返さない。
応答は`Cache-Control:no-store`。開始時はBackendの最新一覧を版確認付きで保存する。

質問取得・次問応答に`mode:full|category|legacy`、`totalQuestions`、`hasNext`を追加する。
旧保存済み応答の3項目省略を受理する。項目を追加する場合は3つをまとめて返す。
新規セッションは一巡で終了し、最後のcompleted Attemptからの次問は409 SESSION_COMPLETED。
旧Sessionは循環動作を維持する。古いAttempt・評価未完了時はSESSION_STATE_CONFLICTを優先する。
終了フラグや総合評価APIは追加しない。最終問への再挑戦は引き続き可能。

有効カテゴリはself_introduction、company_selection、experience、job_change、motivation、career、
strengths、weaknesses、conditions、questions。旧difficultyは既存質問の読取用に保持する。
選択後に質問がなくなったカテゴリの新規開始は409 CATEGORY_UNAVAILABLE。同じ開始要求の成功済み再送を先に返す。

### 管理者の取得・保存

`GET /admin/question-bank`は`{version,updatedAt,questions}`を返す。質問の各項目は
`{id,category,difficulty:"standard",question}`。updatedAtはUTC ISO 8601、初期版0ではnull。
ADMINをBackendで再認可し、未認証401、一般利用者403。応答はno-store。

`POST /admin/question-bank`は`{expectedVersion,questions}`とUUIDのIdempotency-Keyを必須とする。
一覧を全件置換し、成功時200で`{version,totalQuestions,updatedAt}`を返す。
質問1〜100件、本文1〜1,000 UTF-16単位、空白のみ禁止、UUIDの大文字小文字を区別しない重複禁止、
有効カテゴリのみ、未知field禁止。デコード後JSONは1MiBまで、一覧・Sessionの保存上限は350KiB。
Sessionには回答受付・評価完了時の更新に必要な1KiBの余裕を確保し、保存時と新規開始時に検査する。
expectedVersionはJSONの有限な整数値として判定し、`0`・`0.0`・`0e0`は同じ版0として照合する。
真偽値・文字列・小数・範囲外は拒否する。
順番は配列順。IDは編集・移動で保持し、新規追加で発行する。

保存成功記録の照合を版確認より先に行い、後続更新後の再送でも元の応答を返す。
同じキーの本文違いは409 IDEMPOTENCY_CONFLICT、古い期待版は409 QUESTION_BANK_CONFLICT。
管理保存も既存の練習POSTと同じ利用者・キーの識別範囲に含め、異なる操作先での再利用は409とする。
同一一覧の保存では版・日時を変更せず、再送確認記録だけを保存する。
保存結果不明時は同じキー・本文で再確認し、競合時は自動上書きしない。
保存後に開始する新規練習だけへ反映し、既存Session・Attempt・Feedbackを変更しない。

追加エラーは400 QUESTION_BANK_TOO_LARGE、413 REQUEST_TOO_LARGE、上記409各種。
形式は既存の`{code,message}`を維持し、画面はcodeを日本語へ写像する。

### 認証と復旧

実接続はCognito USER_AUTH／EMAIL_OTP。OTP送信・再送は手動で、SDK送信を自動Retryしない。
access／refresh tokenをタブ内に保持し、期限30秒前に更新、同時更新は1件とする。
401で1回更新・同じ要求を再送し、再度401なら再ログインへ移る。403では更新しない。
OTP・challengeはメモリだけに保持し、ID tokenは永続保存しない。
ログアウト後に遅れて返る認証応答で再ログイン状態へ戻さない。
復旧データはClient ID＋subで分離し、同じ利用者だけ復旧する。元の練習へ戻れるようにする。
token・OTP・回答・raw Stateをログに出さない。

旧Mock version1は旧21問のスナップショットを補完し、version2の別キーへコピーする。
元のversion1を削除せず、不整合時は元データを保持して復旧を拒否する。
所有者のない旧Mockデータを実API利用者へ移さない。

更新日: 2026-09-12。設計書v2.3／[ADR-002](ADR-002-frontend-contract-alignment.md)に対応。

## 対象と正本

これは現Frontendと実Backendが共有する採用契約です。旧同期API案は不採用です。Request／Responseの型・制約はZod、HTTP・冪等性・復旧の動作は本書を正本とします。
Schemaの正本は [schemas/index.ts](../frontend/src/lib/api/schemas/index.ts)。MSWとAPI Clientが共用し、TypeScript型をZodから導出します。

Base URLは `NEXT_PUBLIC_API_BASE_URL`。Mockは `/api`。認証Headerの実装はBackend接続工程で追加します。
Request/ResponseはJSON、質問IDを含むIDはUUID、日時はUTC ISO 8601です。質問番号は1始まりです。
FrontendはPOSTのIdempotency-Keyを生成し、BackendはsessionId・attemptId・evaluationIdを生成します。

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
scoreは78.0・7.8e1など有限の整数値も受理し、Backendは整数78として返します。
真偽値・文字列・null・小数・非有限値・範囲外は拒否します。他の型のStrict設定は変更しません。

カテゴリは `job_change`, `motivation`, `strengths`, `experience`, `difficulty`, `career`, `questions`。
回答は空白のみを禁止し、JavaScript文字列長（UTF-16 code unit）で1〜500。100〜300文字は推奨であり制限ではありません。
通常の絵文字は2単位です。本文はtrim・正規化・切り詰めをせず保存・返却します。
カウンターは「現在値 / 500文字 · 100〜300文字がおすすめです」、上限エラーは「500文字以内で入力してください。」です。
500文字制限は回答POSTとFeedbackのanswerへ共通適用し、質問・要約・指摘・回答例には追加しません。

## エラー

形式は `{ "code": "VALIDATION_ERROR", "message": "..." }`。
画面はBackendのmessageを直接表示せず、既知codeを日本語に写像します。

| Status | code |
|---|---|
| 400 | VALIDATION_ERROR |
| 401 | UNAUTHORIZED |
| 403 | FORBIDDEN |
| 404 | SESSION_NOT_FOUND / ATTEMPT_NOT_FOUND |
| 409 | SESSION_STATE_CONFLICT / IDEMPOTENCY_CONFLICT / EVALUATION_NOT_COMPLETED |
| 429 | RATE_LIMITED |
| 500 | INTERNAL_SERVER_ERROR |
| 502 | AI_UPSTREAM_ERROR |
| 504 | AI_TIMEOUT |

評価失敗はHTTP 200の評価GETの `status=failed` と `error` で通知します（例: EVALUATION_FAILED）。通信異常と区別し、既存の評価失敗画面を表示します。error.messageを画面へ直接表示しません。
502/504はHTTPリクエスト自体が失敗した場合の応答です。これだけでは受付済み要求の評価失敗を確定しません。未知コードは汎用表示にします。
Client内のcodeは NETWORK_ERROR / TIMEOUT / ABORTED / INVALID_RESPONSEです。

P1ローカルHandlerのルーティング層は、未知Routeに404・NOT_FOUND、
既知Pathの非対応Methodに405・METHOD_NOT_ALLOWEDを固定messageで返します。
405にはパスに対応するMethodを重複除去・ソートしたAllowヘッダーを付けます（複数はカンマ＋空白区切り）。
主体検証は先に行い、未認証は401です。HEAD／OPTIONSの自動処理は追加しません。
採用済みリソースの404（SESSION_NOT_FOUND／ATTEMPT_NOT_FOUND）は置換しません。

## 冪等性・競合

すべてのPOSTにUUIDの `Idempotency-Key` を必須とします。実BackendではJWT subでユーザーを確定し、ユーザー単位でキーを識別します。同一キー・同一Method・同一Path・同一の検証済みPayloadは保存済みHTTP StatusとResponseを返します。内容や操作先が異なる同一キーは409です。evaluationIdはリソースの識別子であり、冪等キーではありません。
応答消失後の再送は同じキーとPayloadで行い、新しいAttemptを作りません。確定失敗後の再挑戦は新しいキーを発行します。
処理中に異なるキーで回答を送った場合は409。次問操作は現在のcompleted Attemptからのみ許可し、古い結果から巻き戻しません。GETは質問を進めません。
回答POSTは要求とAttempt／Evaluationの関連を永続化して202を返し、評価を継続して結果または失敗を保存します。実BackendのGETは保存済み状態を参照し、評価処理を進める契機にしません。
実Backendでは原子的なキー予約・結果保存が必要です。MSW StoreはFrontendテスト用で、本番の排他制御実装ではありません。

## 通信と復旧

- API Client: 15秒Timeout、呼び出し元AbortSignal、JSONとZod検証。
- 通常GET: 通信失敗・5xxだけ最大1回Retry。POST: 自動Retryなし。
- 評価GET: 自動Retryなし、2秒間隔。30秒で待機案内、120秒で自動確認停止。停止は評価失敗を意味しません。
- 非表示タブ・オフライン・通信エラー・終端状態・画面離脱時はポーリング停止。
- sessionStorageにバージョン付き下書き・未確定要求を保存。現在の質問と再挑戦コンテキストが一致するものだけ復元。
- Reload後はactiveAttemptで評価再開。未確定要求は同じキーで手動確認。保存不可なら画面内操作を継続し、復元不可の案内を表示。
- 古いcompleted／processing Attemptがあっても保存済み未確定要求を優先します。古いfailed Attemptで再入力下書きを消しません。
- 終端後・アンマウント後に経過時間タイマーを止め、新しい評価IDで経過時間と監視を再開します。
- タブを閉じた後の保存は保証しません。

## Mock

### 500文字への切替と旧保存データ

- 質問・操作コンテキストが一致する通常の下書きは501文字以上でも復元します。本文は保持し、送信前に500文字以下への編集を求めます。
- 500文字以下の有効な未確定要求は同じキー・同じ本文で手動確認します。
- 旧501〜2000文字の未確定要求は移行対象外です。保存検証に失敗するとレコード全体が破棄され、同居する下書きも失われ得ます。キー・本文の自動変換や自動送信はしません。
- 旧長文回答を含むMock結果も復元保証外です。Mock全体の保存検証が失敗すると他のMock状態も復元されない場合があります。
- 保存versionは1のままです。互換Schema、移行、一括削除は追加しません。新しい練習・fixtureで動作を確認します。

### Mock動作

7カテゴリ×3問、標準難易度。通常は3回目の評価取得で完了。固定Scoreと文章を返し、画面にサンプル評価と明示します。
開発者ツールで `sessionStorage.setItem('pocket:scenario', 'response_lost')` のように設定できます。
利用可能な値: success / slow / never / validation / unauthorized / not_found / server_error / network_error / response_lost / invalid_response / evaluation_failed / state_conflict。
回答送信のエラーシナリオは原則1回だけ発生します。再現し直す場合はタブのMock保存をリセットしてください。
Storyはparameters.mockで同じWorkerを起動でき、parameters.handlersで上書きできます。Nodeテストは同じHandlerとメモリRepositoryを使います。

## 実Backend接続の条件

[P1 Backend](../backend/README.md)は本契約をメモリ＋Fakeで検証するローカル実装です。
202前の永続化、分散排他、JWT署名検証、非同期起動・停止回復は未実装で、Frontendは未接続です。
[ADR-003](ADR-003-local-backend-foundation.md)と[検証記録](BACKEND_P1_VERIFICATION.md)を参照してください。

本契約のエンドポイント、冪等性、評価状態に対応したBackendと認証方式が必要です。MSWを無効にしBase URLを設定しただけでは旧APIと接続できません。
認証トークンの付与・更新、認証切れ、ログアウト時のQuery Cache／保存情報の分離・破棄を次工程で決定・実装します。
CORSは許可Originを明示し、Authorization／Content-Type／Idempotency-Keyを許可します。
非同期起動・受付保存と起動の整合・重複防止・期限切れ回復・物理データ設計は[次工程の必須事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)を参照します。同じ練習・復旧E2Eを実Backendでも検証します。

参照: [MSW Browser integration](https://mswjs.io/docs/integrations/browser/)、[Next.js Static Exports](https://nextjs.org/docs/app/guides/static-exports)、[Storybook Next.js Vite](https://storybook.js.org/docs/get-started/frameworks/nextjs-vite)。
