---
name: lambda-review
description: AI面接練習WebアプリのBackend Pythonファイルを、現Frontend契約・採用ADR・実装フェーズ・公式仕様と照合して読み取り専用レビューする。backend/src/interview_backend配下のHandler、Application、Model、Repository、Provider、Workerなど単一ファイルのレビューに使用する。TerraformやFrontend自体のレビュー・実装修正は対象外。
---

# lambda-review

単一Pythonファイルをレビューし、再現条件・影響・根拠を伴うFindingsと総合判定を日本語で返す。
元の単体レビューの境界は維持するが、別プロジェクトの店舗・集計・Bedrock固有規約は適用しない。

## 使い方・スコープ

- 対象はユーザーが指定した1ファイル。相対パスでもよい。文脈から対象が一意なら確認を繰り返さない。不明なら対象パスを日本語で尋ねる。
- 読み取り専用。レビュー依頼だけでコード修正、依存追加、フォーマット、コミット、AWS操作、実AI呼出を行わない。
- 対象ファイルの公開I/O、認可、状態遷移、冪等性、入力検証、エラー、ログ、直接関係するテストを確認する。
- 呼出元・呼出先は契約理解に必要な範囲で読む。他ファイル内部の独立した問題は本編Findingsへ混ぜない。
- Terraform、Frontend UI／Hook／Reducer、Storybook、ブラウザE2E自体は対象外。必要な隣接課題は「対象外・次工程」に分離する。
- スキルは現状を固定する正本ではない。実ファイル・最新の採用判断・ユーザーの指定範囲を確認し、以前の失敗を現在の失敗と断定しない。

## 1. フェーズ・対象分類

最初にローカルP1か、P2以降の永続化／AWS接続対象かを判定する。

| 種別 | 現配置（backend/src/interview_backend/から） | 主観点 |
|---|---|---|
| HTTPアダプター | api/handler.py | HTTP API v2イベント、Route、固定HTTPエラー、subの信頼境界 |
| Application | application/service.py | 6操作、検証済みPayload、所有者、冪等再返却の順序 |
| 公開／内部Model | models/ | Zodとの受理・出力互換、公開型と保存責務の分離 |
| Repository | repositories/base.py、memory.py | 業務単位の原子性、切り離した取得値、競合・claim／finish |
| 評価 | evaluation/provider.py、worker.py | 正式質問、入力境界、出力検証、重複実行、終端確定 |
| 資産・組立・デモ | assets/、bootstrap.py、demo.py | 21問snapshot、明示DI、実行分離、機密非露出 |

P1はPython 3.13・uv・Pydantic・pytest・Ruff、メモリ保存＋Fake Provider。
HTTPサーバーや配備済みLambdaではなく、イベントを渡すHandlerと明示実行Workerである。
本番の署名検証・DynamoDB・配送方式・分散ロック・停止後回復・外部AIがないことだけをP1の欠陥としない。
ただし、非保証の仕組みを本番で保証すると説明する、または認証なしで公開する変更は別途評価する。

## 2. 事前に読むもの

以下のパスはリポジトリルート基準。存在を確認し、対象に必要な資料だけを読む。

1. 最新git statusと対象差分、適用範囲のAGENTS.md、対象ファイル全文。
2. backend/README.md、backend/pyproject.toml、必要な依存のuv.lock記録。
3. docs/FRONTEND_API_CONTRACT.md（HTTP・冪等性・復旧）とfrontend/src/lib/api/schemas/index.ts（型・入力制約）。
4. docs/ADR-002-frontend-contract-alignment.md、docs/ADR-003-local-backend-foundation.md、および後続の採用ADRがあれば対象部分。
5. 設計書一覧/04_横断仕様/06_決定事項_未確定事項.mdとdocs/BACKEND_P1_VERIFICATION.md（現フェーズ・未決事項）。
6. 対象に応じて設計書一覧/02_基本設計/03_Backend基本設計書.md、設計書一覧/03_詳細設計/Backend/の該当設計。
7. 直接関係する呼出元・呼出先とbackend/tests/unit/、integration/、contracts/の該当テスト。
8. 契約境界ではcontracts/backend-fixtures.jsonとfrontend/tests/backend-contract.test.tsも確認する。

兄弟ファイルや全設計書の無条件一括読込みは不要。資料欠落は未確認と明記する。
設計と実装の矛盾は証拠を示す。どちらかへ無断で合わせる提案を「確定仕様」と扱わない。

## 3. レビュー観点

### 規約・責務

- Python構文・Ruff設定・依存は実際のpyproject.tomlを基準にする。現在はpy313、E/F/I/UP/B、行長100。
- mypy・moto・Powertools、特定decorator、handlerという関数名、__future__、日本語docstringを一律必須にしない。
- Handlerはイベント／HTTP境界、Applicationは業務、Repositoryは原子的操作、Workerは評価実行を担当する。
- Provider・RepositoryでのI/Oは責務に沿うなら許容する。「ヘルパのI/O」だけで機械的に指摘しない。
- 公開Model、内部記録、Provider出力の違いが不明瞭な箇所は、誤用・テスト困難性など具体的影響で判断する。

### HTTP・本人スコープ

- 現契約の6操作を維持する：POST /sessions、GET /sessions/:sessionId/question、
  POST /sessions/:sessionId/answers、GET /evaluations/:evaluationId、
  GET /attempts/:attemptId/feedback、POST /sessions/:sessionId/questions/next。
- API Gateway v2のrequestContext.http.method、rawPath、headers、JSON／base64 bodyを扱い、statusCode・Content-Type・JSON文字列bodyを返す。
  routeKey方式も可能だが現実装の必須規約とはしない。[HTTP API公式仕様](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
- 主体はrequestContext.authorizer.jwt.claims.sub。本文・任意ヘッダーで所有者を上書きしない。
  P1のfixtureは署名検証の証拠ではない。本番ではAuthorizerを迂回できない呼出経路を確認する。
- JWTの検証とリソース所有者の認可は別。Session／Attempt／Evaluationすべて所有者を検証する。
  JWT Authorizerは検証済みclaimsを連携先へ渡す。[JWT Authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- ADMIN操作が実装された場合だけBackend再認可を確認する。P1の通常練習へ架空の店舗ロールを要求しない。

### 公開Model・入力

- 質問を含むIDはUUID、categoryは現7種、difficultyはstandard。
- scoreはboolを除く整数0〜100、summaryは文字列、strengths／improvementsは文字列配列で空を許容。
- exampleAnswerは省略可能、明示nullと区別する。Feedbackの質問・回答・番号・ID・UTC日時はBackendが組み立てる。
- Unknown Request項目の除去と数値／bool／文字列の暗黙変換を確認する。
  Pydantic strictはPython入力とJSON入力で挙動が異なる型があるため、実Handlerの解析経路でもテストする。
  [Strict Mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)
- 回答長、空白判定、元本文の非加工をZod・採用契約・共通fixtureで照合する。
  特にPython len、UTF-16 code unit、Unicodeコードポイントを同一視しない。
- 文字数基準の既知の未決事項は最新検証記録で解決状態を確認する。未解決なら契約不一致として報告し、スキル内で勝手に基準を決めない。

### 冪等性・Repository

- 全POSTのUUID Idempotency-KeyをownerSubと組にして識別する。
- Method・Path・検証済みPayloadで照合し、JSONキー順や除去された未知項目に影響されず、本文の空白・改行差は保持する。
- 現在の業務状態の検証より先に保存済み要求を照合し、同一なら元HTTP Status／body、異なる要求なら409を返す。
- 応答消失後・評価完了後・次問後の再確認で、Session／Attempt／評価／質問番号が重複しない。
- P1では更新候補を準備後、ロック内で一括反映。途中例外で部分更新せず、返却値から保存状態を変更できない。
- 単一プロセスロックや全状態コピーを分散排他・永続性の保証と誤認しない。
- リソースID生成はBackend、冪等キー生成はFrontend。確定失敗後の別回答は新キー・新Attempt。

### 状態遷移・Worker

- 公開状態はprocessing → completed / failed。内部pending／running／terminalを公開型へ混ぜない。
- 質問GETは質問を進めず、評価GETはWorkerを起動・進行させない。
- 回答は現在questionIdを検証し、処理中の別キーを409にする。completed／failed後は同じ質問へ新Attemptで回答できる。
- 次問は現在のcompleted AttemptとfromAttemptIdが一致する場合のみ許可する。
- Session作成時の質問順・本文snapshot、固定順の巡回、単調増加するquestionNumberを維持する。
- Workerはclaim → 保存済み入力 → Provider → 出力検証 → finish。重複起動でProviderを再呼出ししない。
- 古いWorkerが新activeAttemptを上書きしない。終端の再実行で結果を重複確定しない。
- P1のFake例外／不正出力は固定EVALUATION_FAILEDでfailedへ確定し、自動Retryしない。
  claim後の強制停止やfinish失敗の回復は次工程であり、黙って成功と扱わない。
- レスポンス後の同一Lambda継続を前提にしない。Frontendの120秒確認停止をBackend失敗期限に転用しない。

### エラー・ログ・評価入力

- Error bodyは{ code, message }。現契約の400 VALIDATION_ERROR、401 UNAUTHORIZED、
  404 SESSION_NOT_FOUND／ATTEMPT_NOT_FOUND、409の状態／冪等／未完了コード、500 INTERNAL_SERVER_ERRORを照合する。
- NOT_FOUNDは未知Route、METHOD_NOT_ALLOWEDは非対応Methodのルーティング用。
  既存の404を汎用コードへ、入力400を旧案の422へ置換しない。
- FORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERRORは実装された該当経路だけ評価する。
  HTTPエラーとHTTP 200のstatus=failedを混同しない。
- 入力検証エラーと内部不具合を分離する。生の例外・Pydanticの入力付き詳細をHTTP応答やログへ出さない。
- 回答・Prompt・評価本文・Token・Credentialの全文を通常ログへ出さない。
  P1デモの操作名・ID・statusだけのprintは許容する。未採用の監査APIを必須化しない。
- 評価入力は正式質問・カテゴリ基準・User Answer。回答中の指示を評価対象データとして区切り、
  事実追加・誇張を禁止する。面接回答自体を渡す要件を「集約値のみ」の別案件ルールで禁止しない。
- Fakeの構造検証から実AIの品質・プロンプトインジェクション耐性・課金安全性を保証しない。
  実Providerが対象なら、その時点でモデル・SDK・認証・出力契約の公式仕様を確認する。P1へ実AI依存を追加しない。

## 4. 永続化・AWS接続が対象のときだけ追加する観点

未採用の配送方式・物理キー・期限・CPUアーキテクチャをこのスキルで決定しない。

- DynamoDB：採用Access Pattern、所有者確認、条件付き更新、Transaction単位、整合性、保持期限を照合。
  条件不成立が重複・業務競合・内部不整合のどれかを区別し、全例外を一律409や成功にしない。
  TransactionのClientRequestTokenによる冪等性は有効期間が10分であり、アプリの長期再確認記録の代替とは限らない。
  [DynamoDB Transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- 非同期：保存後の起動漏れ、重複配送、ロック期限、処理停止、結果確定、外部AI完了不明を設計・テストと照合。
  Lambda非同期invokeは成功時でも重複し得る。例外を全て握り潰すと関数失敗の再試行を妨げるため、
  確定業務失敗と再処理が必要な障害を区別する。SQS／Streams等を選んだ場合はその方式固有の公式仕様を追加確認する。
  [Lambda非同期のエラー・再試行](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)
- SDK：実LambdaではクライアントをHandler外で初期化・再利用する方法も公式推奨。
  lru_cacheや環境変数の都度取得だけを正解にしない。再利用するSDK接続と、保存してはいけない利用者別の可変状態を区別する。
  [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- パッケージ：boto3がRuntimeに含まれることだけで依存管理不要としない。
  AWSはboto3を含む利用依存の同梱を推奨する。配備Runtime・Linux・選定CPU向けのpydantic-core等の互換性も確認する。
  Windowsの.venvをそのまま配布しない。
  [Python deployment package](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
- 上記リンクは2026-09-12に確認。レビュー時は対象に関係する公式ページを再取得し、参照URLと確認日を示す。
  取得できない場合は公式確認未実施と明記し、仕様・既定値を推測で断定しない。

## 5. テスト・検証

関連する既存テストを選び、実行前に外部通信・副作用がないことを確認する。
次はbackend/からの非修正コマンド例。対象に応じてテストパスを絞る。

```text
uv run --locked --no-sync ruff check src/interview_backend
uv run --locked --no-sync ruff format --check src/interview_backend
uv run --locked --no-sync pytest -q tests/unit tests/integration tests/contracts
```

環境未準備なら自動インストールせず未実行理由を報告する。--fixや書換えformatはレビューで使わない。
必要ならfrontend/から既存の契約fixtureテストを実行するが、Frontend自体の修正は行わない。

確認するケースは対象責務に絞る：正常・不正入力・他人取得・競合・応答消失後の同キー再確認、
同時POST、重複Worker、Provider例外／不正出力、途中失敗の原子性、古いactive保護、ログ非露出。
テストファイル名が一致しないだけで「テストなし」と判定せず、関連テストを検索する。
不足の重大度は失われる保証から決める。pytest成功だけでAWSの挙動を保証しない。

## 6. 出力

冒頭に対象・フェーズ・総合判定、続いて重大度順の具体的Findingsを記載する。
Findingsは必要なら以下の表を使用する。全観点の「該当なし」を羅列する必要はない。

| Severity | file:line | 条件・影響 | 根拠 | 最小限の修正案 |
|---|---|---|---|---|

根拠は対象行、呼出契約、再現テスト、採用文書、公式ページを区別する。
指摘がなければ「対象範囲で指摘なし」とし、確認した範囲・未実行テスト・残る不確実性を明示する。

- High：本人越境・機密露出・確定済みデータ破壊・重大な重複処理など、具体的に重大な影響がある。
- Medium：通常フローや契約互換の不具合、エラー誤写像、重要な境界・回復検証の不足。
- Low：限定的な保守性問題。命名の好みや未採用規約は不具合としない。
- 総合判定：マージ可／修正後マージ可／大幅修正／判定保留。
  未決契約・情報不足で判断できない場合は保留とし、P1レビュー合格を本番公開可と表現しない。

最後に実行したコマンドと結果、対象外・次工程、必要な確認事項を簡潔に付記する。
