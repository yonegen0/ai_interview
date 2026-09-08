---
name: lambda-review
description: biz-karte の Lambda Python 処理単体を、CLAUDE.md／lambda/README.md・基本設計書／詳細設計書・AWS 公式仕様・ruff/mypy 規約と突き合わせてレビューする。対象は `lambda/functions/<fn>/handler.py`（ハンドラ）／ `lambda/functions/<fn>/*.py`（関数固有ヘルパ：parser/aggregator/rollup/prompt/bedrock 等）／ `lambda/shared/*.py`（共通モジュール）のいずれか 1 ファイル。境界は当該ファイル単体（公開シグネチャ・イベント I/O・DynamoDB アクセス・状態遷移・認可・監査ログ・エラー写像）に限定し、Terraform／フロント（`src/`）／他関数の内部実装／E2E は対象外。
---

# lambda-review

biz-karte の Lambda Python 関数を単体でレビューするための専用スキル。

## 使い方

ユーザーが対象ファイルの絶対パスを 1 つ提示する。引数が無ければ `Which lambda file?` と聞き返す。
パスを受け取ったら以下を順に実行し、最後に **Findings 表** と **総合判定（マージ可 / 修正後マージ可 / 大幅修正）** を出力する。

## 対象ファイルの分類（最初に判定する）

Lambda 側は「トリガ」と「層」で観点を切り替える。

| 種別 | パス | 主目的 | 主観点 |
| --- | --- | --- | --- |
| API ハンドラ | `lambda/functions/fn_*/handler.py`（API トリガ） | API Gateway HTTP API v2 のリクエスト処理 | `with_error_handling`、`require_role`／`require_same_store`、`_ROUTES` ディスパッチ、API 契約整合、OCC、監査ログ |
| 非 API ハンドラ | `lambda/functions/fn_aggregate/handler.py`（S3）／ `fn_diagnose_worker/handler.py`（非同期 invoke） | システム実行イベントの処理 | 冪等性（条件付き UpdateItem）、状態遷移の片道性、外部呼び出しの順序（S3 削除→DDB 遷移）、再試行に耐える設計 |
| 関数固有ヘルパ | `lambda/functions/fn_*/{rollup,parser,aggregator,prompt,bedrock,...}.py` | ドメインロジック／I/O 詳細 | 純粋関数化、I/O と計算の分離、設計書のルール（集約方法・週開始日・会計年度起点・AI 入力制約）と一致 |
| 共通モジュール | `lambda/shared/*.py` | 全関数共通の I/O・認可・キー・時間 | 後方互換、他関数からの利用契約の安定、副作用最小、循環 import 回避 |

**最重要の責務分離**：

- API ハンドラから `with_error_handling` が外れていれば High（共通エラー写像が効かない）。
- ハンドラ内に DynamoDB Item ↔ DTO 変換以外のビジネスロジックがべた書きされていて、`functions/fn_*/<helper>.py` に切り出せる粒度なら Medium（テスト容易性低下）。
- `shared/` モジュールに特定関数固有の知識（特定の `routeKey` リテラル等）が漏れていれば High。
- 関数固有ヘルパが `boto3` や環境変数を直接触っているなら Medium（純粋関数として書ける箇所まで I/O が降りている）。

## スコープ（厳守）

- **対象**: 渡されたファイル 1 つ。
  - 公開シグネチャ（関数引数 / 戻り値型 / 例外型）
  - イベントペイロードの解釈（API GW v2／S3 ObjectCreated／非同期 invoke）
  - 認可（`require_role` / `require_same_store`）
  - DynamoDB アクセス（キー組み立て・GSI 利用・条件式・OCC・冪等性）
  - 状態遷移の片道性／網羅性（ImportJob・Report・Diagnosis）
  - 外部呼び出し（S3／Bedrock／Lambda invoke）の順序と失敗時挙動
  - 監査ログ（`shared.log.write`）の actor／before/after／targetType／requestId
  - 入力バリデーション（422 / VALIDATION の写像）
  - エラー写像（`ApiError` / `ConditionalCheckFailedException` → 409）
  - 同ディレクトリのテスト（`lambda/tests/.../test_<file>.py`）の存在とカバレッジ観点
- **対象外**（指摘しない）:
  - 呼ばれている／呼んでいる他関数の内部実装
  - Terraform（`infra/`）の中身
  - フロント（`src/`）の Hook／コンポーネント
  - Storybook
  - E2E シナリオ（`tests/integration/`）の中身
  - 直接関係のない他ヘルパへの改善提案

スコープを越える指摘は「Out of Scope (参考)」として 1 セクションにまとめ、本編の Findings には混ぜない。

## 事前読み込み（並列）

1. レビュー対象ファイル全文。
2. 同じ関数ディレクトリの兄弟ファイル（`functions/<fn>/*.py`）を全部。
3. `lambda/shared/error.py`（`ApiError` / `with_error_handling` / 409 自動写像）。
4. `lambda/shared/http.py`（API GW v2 のイベント解析・`json_response`）。
5. `lambda/shared/auth.py`（`Claims` / `require_role` / `require_same_store`）。
6. `lambda/shared/dynamo.py`（`get_table` / `pk_*` / `sk_*` / `gsi*_*`）。
7. `lambda/shared/log.py`（`write` の引数規約と GSI2 同期）。
8. `lambda/shared/time.py`（JST / periodKey / `utcnow_iso`）。
9. 対応するテスト：`lambda/tests/functions/<fn>/test_<file名>.py` または `lambda/tests/shared/test_<file名>.py`。
10. ルート `CLAUDE.md` と `lambda/README.md`。
11. **設計書**：
    - `基本設計書/基本設計書_経営健康診断システム.md` — 全体像／ドメイン／状態遷移／API 一覧／AI 制約／生データ非保持
    - `基本設計書/インフラ基本設計書.md`
    - `詳細設計書/00_共通設計.md` — エラー処理／queryKey／指標定義／HTTP ステータス表
    - `詳細設計書/インフラ詳細設計書_Terraform.md` — §5.1 関数表／§5.3 監査ログ／§5.4 認可マトリクス／§5.5 OCC／§5.6 冪等性／§2.1 キー設計
    - 該当画面の `詳細設計書/0X_*.md`（`Glob` で `詳細設計書/**/*<feature>*.md` を探す。例：`fn_reports` → 04／05、`fn_imports` → 03、`fn_diagnose_*` → 06、`fn_logs` → 09、`fn_settings` → 08）
12. `lambda/ruff.toml` ／ `lambda/pyproject.toml`（`mypy` 設定）。

`AGENTS.md` は本リポジトリに存在しないので読まない。

## レビュー観点チェックリスト

各観点を順に確認し、該当があれば Findings に **`file:line` 付き** で記録する。空でも観点名は出力する（「該当なし」を明示）。

### 1. 規約・スタイル（CLAUDE.md ／ ruff ／ mypy）

- ドキュメント／コメントは日本語（グローバル CLAUDE.md）。
- モジュール先頭に docstring があり、**設計書参照**が明示されている（`lambda/README.md` の既存実装に揃える）。
- 公開関数 / クラスに docstring が付いている。
- `from __future__ import annotations` を使い、型は文字列遅延評価。
- 型は Python 3.12 構文（`list[T]` / `dict[K, V]` / `T | None`、`Optional[T]` を避ける）。
- `Any` は境界（イベント・boto3 戻り値）のみ。内部ロジックで広がっていれば指摘。
- ruff の `select = ["E","F","W","I","B","UP","N","SIM","RET"]` に違反していそうな箇所（未使用 import、可変既定引数、`isinstance` チェーン、複雑な早期 return など）を機械的に拾う。
- `# noqa` の濫用が無い（特に `BLE001` は最上位 handler や `except` で意図が説明できる場面のみ）。
- 推測実装でない（設計書／公式ドキュメント／既存兄弟ファイルに根拠がある）。

### 2. 責務分離（biz-karte 固有）

- **API ハンドラ**は薄く保ち、`_ROUTES` ディスパッチ＋認可＋入力検証＋DDB I/O 呼び出し＋DTO 変換に留める。長い計算ロジックは関数固有ヘルパへ。
- **関数固有ヘルパ**は基本的に純粋関数。`boto3` クライアントや `os.environ` を直接見ない（I/O はハンドラ側へ）。
- **`shared/`** に特定関数固有の知識（具体的な routeKey／targetType の挙動分岐）を持ち込んでいない。共通モジュールは横断的にしか参照しない。
- `boto3.resource` / `boto3.client` の生成は `lru_cache` で 1 度だけ（コールドスタート最適化／`shared/dynamo.py` の既存パターン）。

### 3. シグネチャ設計

- ハンドラ関数名は `handler`、シグネチャは `(event: dict[str, Any], context: Any) -> dict[str, Any]`。
- 第 1 引数のテナント境界が明示的に出ているか（API ハンドラなら `path_param(event, "storeId")` を先頭付近で呼んでいる）。
- 関数固有ヘルパは引数を **値オブジェクト**（dict・dataclass・TypedDict）で渡し、`event` をそのまま渡し回していない。
- 戻り値型に `dict[str, Any]` を多用しすぎていない（公開する DTO は TypedDict/NamedTuple で型付けする選択肢がある）。
- 命名は `snake_case`、定数は `UPPER_SNAKE_CASE`、内部関数は `_` プリフィクス。

### 4. API ハンドラ規約（API トリガの場合）

- 関数全体が `@with_error_handling` で包まれている（`shared/error.py`）。
- ルーティングは `event["routeKey"]` を `_ROUTES` dict で引く。未マッチは `ApiError(404, "NOT_FOUND", ...)`。
- 認可は `require_role(event, {...})` → `require_same_store(event, store_id)` の順で **両方** 呼ぶ（多層防御）。
- ロール集合がインフラ詳細設計書 §5.4 の認可マトリクスと一致。
  - `fn_settings`：GET owner+staff+admin／POST admin／metric-defs 全ロール／templates owner+admin
  - `fn_imports`：owner / staff / admin
  - `fn_reports`：confirm/rollup は owner、参照は owner+staff+admin
  - `fn_logs`：admin
  - `fn_diagnose_start`：owner
- レスポンスは `json_response(status, body)` 経由（直接 dict を返さない）。
- 入力バリデーション失敗は `ApiError(422, "VALIDATION", ...)`。`400` は path/method/parsing 系の構造的不正のみ。
- `parse_body(event)`／ `path_param(event, ...)` ／ `query_param(event, ...)` ／ `request_id(event)` を `shared/http.py` から使い、`event` 直触りで書き直していない。

### 5. 非 API ハンドラ規約（S3 ／ 非同期 invoke の場合）

- **S3 ハンドラ**：例外を関数の外へ逃さず、レコード単位で try/except し失敗を `_mark_failed` 等で状態遷移として記録する（`fn_aggregate` の既存パターン）。複数 `Records` のうち一部失敗で残りを処理する設計か。
- **非同期 invoke ハンドラ**：必須キー欠落のイベントは `logger.error` + 早期 return（`with_error_handling` は使わない、API 経路ではないため）。
- 終端状態（`raw_purged` / `completed` / `failed`）に対して再度の遷移を試みていない（`ConditionExpression` でガード）。
- 全例外を捕まえる箇所には `# noqa: BLE001` の意図コメントが残せる構成になっている。

### 6. DynamoDB アクセス

- キーは `shared/dynamo.py` の `pk_*` / `sk_*` / `gsi*_*` を使い、ファイル内で `f"STORE#{store_id}"` などのリテラルを散らさない（キー設計変更時の影響範囲）。
- `IndexName` 定数（`GSI1_NAME` / `GSI2_NAME`）を使う。リテラル `"GSI1"` を直書きしない。
- `KeyConditionExpression` には `boto3.dynamodb.conditions.Key` / `Attr` を使う（生文字列の `=` を組み立てない）。
- `UpdateExpression` で **予約語**（`status` / `version` / `name` / `timestamp` 等）を直接書かず、`ExpressionAttributeNames` で `#s` 等にエイリアスしている。
- Resource API は `Decimal` を返すので、API レスポンス／計算経路で `Decimal` の扱いが破綻していない（`json_response` の `_json_default` 経由で int/float 化されることを前提に、内部で `Decimal == int` 比較や `% 1` 等の落とし穴が無い）。
- 一覧 Query で `Limit` を扱う場合、`LastEvaluatedKey` の継続トークンも返す設計か（設計書がページネーション要求している場合）。

### 7. OCC（楽観ロック）／ 冪等性（インフラ詳細 §5.5 / §5.6）

- 確定・状態遷移系の `update_item` は **`ConditionExpression` 必須**。`version = :v AND #s = :from` のような前提条件を持つ。
- `ConditionalCheckFailedException` のキャッチが正しい。
  - API ハンドラ：**キャッチせず外に逃がす**（`with_error_handling` が 409 / `CONFLICT` に写像）。自分で try/except する場合は同じ意味になっているか確認。
  - 非 API ハンドラ：`_try_transition` のように **`False` を返して黙って終了**（at-least-once 多重起動の正常系）。
- `version + 1` をインクリメントしているか（OCC）。
- 終端状態（`raw_purged` / `confirmed` / `superseded` / `completed` / `failed`）への二重遷移を `ConditionExpression` で防げているか。
- `fn_aggregate`：**DDB 状態遷移 → S3 削除 → DDB 状態遷移** の順序を守っているか（生データ非保持の二重化：基本設計書 §11）。S3 削除より先に `raw_purged` へ遷移すると、削除失敗時に整合性が崩れる。

### 8. 状態遷移整合（基本設計書 §10）

- **ImportJob**：`uploaded → validating → aggregating → aggregated → raw_purged`、失敗は `failed`。`raw_purged` から戻らない。
- **Report**：`draft → confirmed → superseded`。`superseded` から戻らない。`confirm` は `status=draft` の条件付き。`rollup` 時に既存上位 `confirmed` を `superseded` に遷移してから新規 `draft` を作る順序。
- **Diagnosis**：`generating → completed/failed`。`generating` のみから `completed` / `failed` へ条件付き遷移。
- 遷移コードと設計書の図が一致しない箇所は High。

### 9. 監査ログ（`shared/log.write`）

- 状態変更を行う全 API／非 API 関数が処理完了時に `log_write(...)` を呼んでいる（`fn_logs` 自身を除く）。
- 引数：
  - `store_id` / `target_type` / `target_id` / `action` / `actor` / `request_id` 必須。
  - `before_status` / `after_status` を **状態遷移を伴う場合は必ず** 詰める。
  - `target_type` は `"import_job" | "report" | "diagnosis" | "settings"` のいずれか。
  - `actor` は `Claims`（API は `require_role` の戻り値）。システム実行は `SYSTEM_ACTOR` 定数（`fn_aggregate`／`fn_diagnose_worker` のパターン）。
  - `request_id` は API なら `request_id(event)`、非 API なら `s3-<jobId>` / `async-<diagnosisId>` の規約。
- 例外パスの監査ログ抜けが無い（成功時のみログを書いて失敗時は黙る、になっていないか）。

### 10. エラー写像（`詳細設計書/00_共通設計.md §5`）

- HTTP ステータスと `ApiError.code` の対応が表通り：
  - 401 / `UNAUTHORIZED`（認証情報の不正、`get_claims` で扱う）
  - 403 / `FORBIDDEN`（権限不足／テナント越境）
  - 404 / `NOT_FOUND`（対象不在）
  - 409 / `CONFLICT`（OCC 競合・`ConditionalCheckFailedException` から自動写像）
  - 422 / `VALIDATION`（入力検証エラー）
  - 500 / `SERVER`（想定外、`with_error_handling` が丸める）
- 400 を `VALIDATION` で返している箇所は意図的か（構造的不正は 400、業務的検証は 422 という棲み分け）。
- 例外メッセージに **個人情報・スタックトレース** を漏らしていない。
- `logger.exception` は 500 系（想定外）でのみ使い、業務エラー（401/403/404/409/422）では使わない。

### 11. AI／生成・S3／Bedrock 呼び出し（該当時のみ）

- **AI 入力は集約値のみ**（基本設計書 §9.3）。`fn_diagnose_worker` 配下で生データ／個人情報を `prompt.py` ／ `bedrock.py` に渡していない。
- プロンプト構築は `prompt.py` に集約し、`handler.py` 側で直接組み立てていない。
- `bedrock.py` の単一 IF `generate_diagnosis(...)` に Bedrock 呼び出しが閉じ込められている（インフラ詳細 §6.4）。モデル ID／リージョンは環境変数経由。
- 完了時の `modelInfo` に `provider` / `modelId` / `trainingOptOut: true` を記録している（基本設計書 §7.5）。
- **S3 削除順序**：`fn_aggregate` は `aggregated` 遷移成功後に `delete_object` し、その後 `raw_purged` 遷移という順を守っている（§7 でも触れたが §11 の AI/S3 観点として再掲）。

### 12. 入力バリデーション

- ハンドラ境界の最低限のガードがある：空文字 `storeId`、整数フィールドの `isinstance(v, int) and not isinstance(v, bool)`、必須キー欠落、`granularity ∈ {weekly, monthly, yearly}`、`periodKey` 形式（`W:` / `M:` / `Y:`）。
- 値域チェックは UI（zod）と API（Lambda）の両方で必要（多層防御）。Lambda 側で省略しているなら指摘。
- ファイル解析（CSV/XLSX）は失敗を例外で外に投げず、`failed` 状態遷移として記録する設計か。

### 13. テスト（同階層 `lambda/tests/.../test_<name>.py`）

- 対応テストが存在する。無ければ High（`pytest` + `moto` でユニットテスト前提）。
- API ハンドラ：401／403（テナント越境）／404／409（OCC）／422（入力）／200 のケースが揃っている。
- 非 API ハンドラ：多重起動（同一イベント 2 回）／状態遷移ガード／失敗時の `failed` 遷移／生データ削除順序を検証している。
- DynamoDB／S3 は `moto` フィクスチャを使い、現実の AWS を叩いていない（`conftest.py` の既存パターン）。
- Bedrock は実呼び出しでなく `monkeypatch` でモック。

### 14. 非機能

- `print()` を本番経路に残していない。ログは `logging.getLogger(__name__)`。
- 環境変数アクセスは関数呼び出し時に都度行う（モジュール読み込み時の `os.environ["X"]` 直参照は、コールドスタート前に env が無くて落ちる事故の原因になる。`shared/dynamo.py` の `get_table` パターンに揃える）。
- 循環 import 回避のための関数内 `from shared.error import ApiError` のような既存パターンを壊していない。
- `boto3` / `botocore` 直 import は OK（ランタイム同梱）。`requirements.txt` に書いていない外部依存（`openpyxl` / `python-ulid` 等）を新たに import していたら、関数固有の `functions/<fn>/requirements.txt` への追記が必要 → 指摘。
- `architectures=["arm64"]` で動く前提（ネイティブ依存のホイール互換性）。

## 出力フォーマット

```
# Review: <lambda file relative path>

## 分類
- 種別: API handler / S3 handler / async worker / function helper / shared module
- 対応関数: <fn_xxx>（shared の場合は "shared"）
- トリガ: API GW v2 / S3 ObjectCreated / Async Invoke / N/A
- 対応設計書: <参照した設計書のパス>（無ければ "設計書未確認"）

## Findings

| # | Severity | file:line | 観点 | 指摘 | 根拠 | 提案 |
|---|----------|-----------|------|------|------|------|
| 1 | High     | …         | …    | …    | …    | …    |

## 観点別サマリ
1. 規約・スタイル: ✓ / 指摘あり
2. 責務分離: …
3. シグネチャ設計: …
4. API ハンドラ規約: …（該当時のみ）
5. 非 API ハンドラ規約: …（該当時のみ）
6. DynamoDB アクセス: …
7. OCC / 冪等性: …
8. 状態遷移整合: …
9. 監査ログ: …
10. エラー写像: …
11. AI / S3 / Bedrock: …（該当時のみ）
12. 入力バリデーション: …
13. テスト: …
14. 非機能: …

## Out of Scope (参考)
- （当該ファイルの責務を越えるが気付いた点を 1〜3 件まで。無ければ "なし"）

## 総合判定
**マージ可 / 修正後マージ可 / 大幅修正** — 一行コメント
```

## 重大度の基準

- **High**：規約違反（`Any` の蔓延／`with_error_handling` 欠落）、認可（`require_role`／`require_same_store`）の漏れ・誤集合、テナント越境を許す実装、OCC の `ConditionExpression` 欠落、冪等性ガード欠落（条件付き UpdateItem を使わず多重実行で破壊的）、生データ削除と DDB 遷移の順序逆転、AI に生データを渡している、終端状態への再遷移を許す、監査ログ書き漏れ（特に状態遷移の `before/after`）、テスト未作成、`shared/` への関数固有知識混入、ハンドラ外の `os.environ` 直参照によるコールドスタート起動失敗リスク。
- **Medium**：バリデーション網羅性不足、エラーコード写像のズレ（400／422 の取り違え等）、命名規約のブレ、DDB キーリテラル直書き、`IndexName` のリテラル直書き、ヘルパが I/O を抱え込んで純粋関数化されていない、設計書と細部（ロール集合・期間境界・週開始日）で齟齬、`logger.exception` の濫用。
- **Low**：docstring 文言、型注釈の細部、内部関数名の好み、`# noqa` の理由コメント追加余地。

## やってはいけないこと

- 対象ファイルを **編集しない**（読み取り専用レビュー）。レビュー結果のみ出力する。
- 推測でコードを書かない。設計書 / `lambda/README.md` / 公式ドキュメント / 既存兄弟ファイルを根拠にする。
- 他関数 / Terraform / フロントへの波及指摘を Findings 表に混ぜない（Out of Scope 欄へ）。
- 設計書が見つからない場合は「設計書未確認」と明示し、API 契約・認可マトリクス照合は `lambda/README.md` と既存 shared 実装の自己整合に留める。
- `boto3` / `mypy_boto3_*` の API バージョン差で迷ったら、公式ドキュメント（AWS SDK for Python v1 / boto3 latest）と既存兄弟ファイルの使い方を優先する。
