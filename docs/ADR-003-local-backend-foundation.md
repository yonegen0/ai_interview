# ADR-003: 現Frontend契約でローカルBackendを先行実装する

日付: 2026-09-11。状態: 採用（P0・P1）。[ADR-002](ADR-002-frontend-contract-alignment.md)を継続する。

## 背景

旧添付計画の同期POST /evaluations、Session不要、Frontend生成evaluationIdを冪等キーにする案、
S/A/B/C評価は採用済みFrontend契約と異なっていた。
新しい承認計画は6 API、202受付、評価GET、100点Feedback、全POST冪等性を維持する。
全AWS設計の確定をローカル業務検証の前提にせず、保証範囲を段階化する。

## 判断

1. 初回はPython 3.13、uv、Pydantic、pytest、Ruff。OpenAI・boto3・Web Frameworkは追加しない。
2. メモリRepositoryでSession／Attempt／Evaluation／冪等要求／Worker管理情報を扱う。
3. 6操作とWorker claim／finishをRepository境界とし、単一プロセスのロック・copy-on-writeで一括反映する。
4. 全POSTはownerSub＋UUIDキーで照合し、現在の業務状態より先に保存応答を再返却する。
5. 現行21問をBackend資産として継承。約100問への拡充は後続で、初回の完了条件ではない。
6. HTTP APIイベントをHandlerへ渡すローカルテスト・CLIで開始する。署名検証済みイベントのfixtureを使う。
7. 回答をメモリへまとめて保存して202。別Workerを明示実行し、GETは保存状態のみを読む。
8. ProviderはFakeのみ。出力を検証し、管理情報はBackendが追加する。本文／内部例外をログへ出さない。
9. Frontendの画面・Hook・Reducer・復旧保存・URL・通信Retryを維持する。認証接続はP6。
10. 初回リリースは管理者登録ユーザーの認証付き練習。履歴・お気に入り・管理画面は後続。

## 契約補足

未知Routeの404はNOT_FOUND、既知Pathに対する非対応Methodの405はMETHOD_NOT_ALLOWED。
2026-09-12追記：405には対応MethodのAllowヘッダーを付与する。主体欠落の401を先に判定する。
回答はFrontend・BackendでUTF-16単位1〜500文字へ変更し、100〜300文字推奨・本文非加工を維持する。
scoreは有限の整数値表現を受理し整数で出力する。旧長文pending／Mock結果の移行は行わない。
これはルーティング層だけの追加で、採用済みリソースの404コードは置換しない。
Unknown RequestプロパティはZodと同様に除去する。省略可能exampleAnswerにnullを返さない。
Frontend停止時間の120秒をBackendの実行期限に転用しない。

## 保証範囲と代償

単一プロセスでの原子性と重複起動抑止を検証する。全状態コピーは小規模ローカル検証用。
永続性、分散排他、Worker停止回復、JWT署名、AI課金、DynamoDB Transactionは保証しない。
ローカルイベントへ任意subを渡せるため、Handlerを認証なしで公開してはいけない。
本番向けの「202以前に永続化する」という契約をP1のメモリ保存で達成したとは扱わない。

## 継続する方針と次の判断

Cognito、HTTP API JWT Authorizer、DynamoDB 1テーブル、OpenAI、Terraform、
Private S3＋CloudFront OACという将来方針を維持する。
Lambdaの3責務は将来構成であり、初回に空のadmin実装や3つの配備単位を作らない。
P2で非同期起動、保存と配送の整合、物理キー／GSI／Transaction、ロック期限と回復、
AI完了不明時の再実行・課金、保持・削除・上限・監視を確定する。
P3でDynamoDB Local、P4でAWS dev＋Fake、P5で実AI、P6で認証・Frontend接続、P7で品質・公開判定。

## 証拠

[Backend README](../backend/README.md)、[実装計画](../AI面接練習Webアプリ｜実装計画.md)、
[必須事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)、
[検証記録](BACKEND_P1_VERIFICATION.md)。
