# Backend P1 検証記録

更新日: 2026-09-12。開始時HEAD: `37b5f7f`。ステージング・コミット・AWS操作・公開なし。

## 現在の判定

**P0・P1は完了**と判定します。2026-09-12に回答をFrontend・Backend共通の
UTF-16 code unit 1〜500文字へ確定し、共通fixture・全テストで整合を確認しました。
100〜300文字の推奨、本文非加工、6 API、冪等性、明示Workerは維持しています。

FrontendはZodのmaxへ依存せずJavaScript `string.length`を明示検証します。
通常の絵文字は2単位で、絵文字250個は受理、250個＋日本語1文字は拒否します。
旧501〜2000文字の未確定要求・Mock結果は移行対象外です。通常の長い下書きは保持し、
500文字以下へ編集してから送信します。保存version・互換Schema・一括移行は追加していません。

Backendレビュー指摘として、有限の整数値score（78.0・7.8e1）を整数として受理し、
bool・文字列・小数・NaN・Infinity・範囲外を拒否するよう修正しました。
既知Pathの405には対応MethodのAllowヘッダーを返します。

### 変更前の履歴

変更前は回答上限2000で、Zod 4.5.4のコードポイント数とBackendのUTF-16単位に差がありました。
Frontend共通fixtureは64成功／1失敗（emoji over limit）、Backendは132件成功でした。
日時の秒省略不一致はそれ以前に秒必須のUTC ISO形式へ修正済みです。

## 実装した内容

- Python 3.13・uv.lock・Pydantic・pytest・Ruffの独立Backendプロジェクト。
- 6 API、UUID・型・回答検証、JWT Authorizerイベントのsubによる本人スコープ。
- 21問継承、Sessionごとの質問snapshot、再挑戦・次問・巡回。
- メモリRepositoryの単一プロセスロックとcopy-on-write、全POSTの保存済み応答再返却。
- API受付と独立した明示Worker、Fake Provider、出力検証、固定失敗状態。
- 同時POST、同時／連続Worker、途中失敗、古いactive保護、取得値の変更防止のテスト。
- API Gateway形式のHandler、base64 body、固定HTTPエラー、内部例外非露出。
- 共通JSON fixture、Python実Handler応答比較、Frontend Zod／MSW質問一致テスト。
- CLIデモ、Backend CI、README、ADR-003、P0〜P7実装計画、決定事項・入口の更新。

## 検証結果

| 確認 | 結果 |
|---|---|
| uv sync | 成功。Python 3.13.13／uv 0.11.8、uv.lock生成 |
| uv run --locked ruff check . | 成功（2026-09-12） |
| uv run --locked ruff format --check . | 成功、24ファイル |
| uv run --locked pytest -q | 184件成功（2026-09-12） |
| CLIデモ | 成功。作成→回答→明示Worker→結果→同一要求→次問→他人404 |
| Frontend lint | 成功（前回実行） |
| Frontend typecheck | 成功（前回実行） |
| Frontend限定再検証 | 契約・入力・復旧の3ファイル、122件成功 |
| Frontend lint／typecheck | 成功（2026-09-12） |
| Frontend全test | 27ファイル・350件成功（LCP警告のみ） |
| production build／mock build | ともに成功。全5静的Routeを生成 |
| Storybook build | 成功。chunk size警告のみ |
| E2E | 8件中7件成功。500文字・絵文字境界と375／768／1280px成功。既知WebP 1件のみ失敗 |
| GitHub Actions | workflow追加のみ。リモート実行は未実施 |
| 更新文書リンク | 136件確認、参照先欠落なし |
| git diff --check | 成功（既存Git設定によるLF→CRLF案内のみ） |

通常sandbox内ではuvキャッシュアクセス拒否・Vitest spawn EPERMを確認しました。
通常sandbox内ではuvキャッシュアクセス拒否・Vitest spawn EPERMを確認し、承認付き実行で完了しました。

## 既知のFrontend画像問題

[前回のFrontend検証記録](FRONTEND_ALIGNMENT_VERIFICATION.md)にあるWebP実寸1254pxと
E2E期待値512pxの不一致は未修正です。P1の対象外、P7では修正してE2E全件成功が必要です。
今回、画像の期待値・テスト除外・画像ファイルの変更はしていません。

## 保証しない事項・次工程

メモリはプロセス終了で失われます。複数Lambdaの排他、永続化、起動漏れ、
claim後のWorker停止回復、JWT署名、実AI品質・課金・Timeout、DynamoDB Transactionは未検証・未実装です。
FrontendはMSWを継続し、このBackendに未接続です。公開用Handlerとして配備しないでください。

P2では非同期起動、受付と配送の整合、期限・回復・重複、AI完了不明、物理キー／GSI／Transaction、
保持・削除・利用上限、Lambda／IAM、監視を確定します。
詳細は[決定事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)と
[実装計画](../AI面接練習Webアプリ｜実装計画.md)を参照してください。
