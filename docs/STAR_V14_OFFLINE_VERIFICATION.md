# STAR Ver.1.4 オフライン実装・検証報告

正式ステータス: `STAR_V14_OFFLINE_VERIFIED_PENDING_DEPLOY_APPROVAL`

Branch: `codex/star-assist-v14-offline-20261010`。基準main: `bc0919e13477f4d86609e1c7ed51590e118a8fd2`。
最終commit HEADとworktree位置はルートの `docs/STAR_V14_IMPLEMENTATION_RESULT_20261010.md` に記録する。
添付の未確定扱いより、ユーザーの最終計画で承認された通常下書き/業界・企業名14日を優先した。

## 結果

Backend/Frontend/FakeProvider/共有Mock V4/補助API/回復/テストまで実装した。V2の30点・400コードポイント・最大3深掘り・累積正式履歴・4操作・初回Evaluation IDとV1の100点・500 UTF-16・旧pending/保存bytesを回帰確認した。

|実行コマンド（各対象ディレクトリ）|最終実測|
|---|---|
|`python -B -m ruff check .`|PASS|
|`python -B -m ruff format --check src tests skills`|143ファイル PASS|
|`pytest -q --tb=short -p no:cacheprovider --basetemp <fresh> -m "not dynamodb and not aws_e2e"`|**1501 PASS / 1 SKIP / 57 deselected**|
|`python -B -m interview_backend.demo`|V1 demo PASS、Memory＋Fakeだけ|
|`npm run lint` / `npm run typecheck`|PASS、lint 0 error / 0 warning|
|`npm test`|**662 PASS（unit 272、Storybook browser 390）**、63 files|
|`npm run build` / `npm run build:mock` / `npm run build-storybook`|すべてPASS、最終の画面説明文修正後にも再ビルド|
|`npm run test:e2e`|**37 PASS**、2.1分|
|STAR補足E2E `--grep 'application response\|three editable\|V4 keeps'`|**5 PASS**、39.5秒（37件と重複、合算しない）|
|`terraform fmt -check -recursive terraform`|PASS|
|隔離コピーの `init -backend=false -input=false -lockfile=readonly` / `validate`|4 roots PASS|
|隔離コピーの `terraform test`（aws mock_provider）|service 48＋bootstrap 4＝**52 PASS / 0 FAIL**|
|`git diff --check`|PASS|

SKIP 1件は既存のWindows symlink作成権限がない場合のprivacy gate試験。57件はユーザーが禁止した実DynamoDB/AWS E2Eをmarkerで除外した。Baseline166/140は事前確認であり、この表の実装後件数とは区別する。

初回検証では旧「再挑戦は空欄」のE2E期待値、増えたSTAR ConditionCheck/4領域のfixture、worktreeの依存共有/ローカルサーバー設定を修正した。失敗ログも保全し、上表はその後の成功結果を示す。最後の変更は画面説明文だけであり、lint/typecheckと3ビルドを再確認した。

## 要件→実装→試験

Backendの新規受入は `backend/tests/unit/test_star_assist.py`、SDK境界は `test_dynamodb.py`。Frontendは `tests/star-assist.test.ts`、`tests/e2e/star-assist.spec.ts` と既存回帰。該当コードの詳しい状態/物理キーは[設計](STAR_V14_DESIGN.md)を参照。

|ID|要件→コード→実行した試験|結果/範囲|
|---|---|---|
|T01|Pydantic/Zod/codec/共有fixture → Backend STAR/SDK Stubber、TS STAR契約|PASS、未知項目・不整合状態/ID・Unicode/hash/UUID|
|T02|owner/session/question/origin → STAR context API、Coaching回帰、2-owner API試験|PASS、JWT sub以外のowner入力拒否、別本人404|
|T03|live/expiresAt → 固定時計境界とブラウザの期限切れserver-bound cache|PASS、GET延長なし、TTL物理削除前でも失効|
|T04|設定世代＋version → 期限後再作成/同versionの旧世代拒否|PASS、保存世代のABA対策|
|T05|CAS/直列save/競合UI → 同版thread保存、実2ページ|PASS、入力保持・勝者1件・自動版差替えなし|
|T06|StarRequest/再確認 → 保存応答消失→別タブ更新→元receipt照会|PASS、本人要求の成功と最新内容を分離|
|T07|star_post/recover → 同key原応答・別Payload拒否・404時同key再送|PASS、receipt再現と既存回答/管理namespace保全|
|T08|正式受付transaction/PUT更新専用 → save/submit順序・旧PUT/物理削除|PASS、閉じた下書きの再作成不可|
|T09|queued取消＋quota返却 → 正式回答が先に確定|PASS、Provider 0回・予約返却1回|
|T10|started後の正式送信/終端 → 結果遅着/本文scrub|PASS、消費維持・下書き/通常本文を復活させない|
|T11|start/finish再確認・Recovery → commit後応答喪失、確認不能、二重Recovery|PASS、同実行/同結果だけ再確認、二重呼出し/返却なし|
|T12|独立JST quota/active pointer → 20/600境界・同key4並列・2人最後1枠・SDK transaction|PASS、1文脈1予約・global競合の勝者1人|
|T13|month_for/CommitWindow → JST月末/年跨ぎ・旧月の返却|PASS、受付月を再送で変更しない|
|T14|useAnswerOperation/Feedback.answer → pending/通常復元/再挑戦/深掘り回帰|PASS、初回正式回答の初期表示、3深掘り/累積履歴維持|
|T15|3案RHF/apply → 全3幅の選択前編集・切替・上書き確認/Escape・反映中入力|PASS、未採用案を採点しない、遅い反映で上書きしない|
|T16|recovery v3/補助ヘッダー → 旧pending・401/再送・application期限/正式hash|PASS、旧Bodyを変換せず、成功済み受付は期限後も再現|
|T17|events/codec → 下書き/REMOVE無視・旧イベント・SQS/Streams種別不一致|PASS、誤ったProviderへ渡さない|
|T18|Recovery rotation/cursor → 評価150件滞留、4領域巡回、時間予算/競合|PASS、STARを初巡回で回復、旧複数ページ処理維持|
|T19|IndexedDB marker/import → V1/V2/V3取込、異なる旧V3再起動、V4破損|PASS、元キー保持・再投入/merge/fallbackなし|
|T20|共有transaction/owner scope → 閉タブ復元・実2ページ・owner切替|PASS、別本人の本文復元なし|
|T21|code point guards → 400/401・過長下書き・原文/旧UTF-16回帰|PASS、原文切詰め/正規化なし|
|T22|MUI fields/Dialog → 375/768/1280、Tab移動/Escape、障害・focus・Storybook|PASS、横overflowなし、3幅の目視確認済み|
|T23|Memory MSW/serial idle save → 30 actor/120 HTTP操作・未変更2秒以上|PASS、未変更保存0件、測定は下記|
|T24|固定error/安全ログ → 本文/メモ/JWT除外・既存operational log回帰|PASS、機密本文を例外ログに出さない|

## 実測と未検証

30本人相当の同時処理ではcreate/question/context/saveの120 HTTP操作をMemory/MSW上で実行した。Vitest JSONのケース時間は **343.6 ms**（単一実測）。この試験でEvaluationとquotaは作成されない。未変更画面で保存要求0件もブラウザで確認した。AWSの30人性能や既存正式Gateの合格値を表さず、Gateは変更していない。

375/768/1280pxの画像を保存し、横overflow、入力/ラベル/3案/選択/反映の配置を目視確認した。keyboard Tab、Dialog Escape、通信応答消失、2タブ、閉タブ、owner切替をオフラインで確認した。

今回の範囲の未達はない。実AWS上のtransaction/IAM/GSI/Streams/Lambda/SQS/Cognito/Recovery、TTL物理削除、実負荷・課金は未検証。保証するのは期限後API拒否であり、TTLの物理削除時刻は保証しない。
実STAR ProviderはFake固定。実OpenAI接続、モデル可用性/生成品質、実token/価格、実AIのprompt injection試験は未実施。gpt-6-lunaは未検証候補。Fakeの実API費用0を実AIの料金推定に用いない。実Provider導入と費用見積りは[配備前承認事項](STAR_V14_DEPLOYMENT_APPROVAL_REQUIRED.md)に残した。

## 変更ファイル一覧

以下 **70ファイル**。依存追加、package lock、Terraform provider lock、workflowの変更なし。

|ファイル|目的|
|---|---|
|`backend/src/interview_backend/api/handler.py`|PUT/補助ヘッダー・no-store・固定エラー|
|`backend/src/interview_backend/application/service.py`|正式回答の任意application参照|
|`backend/src/interview_backend/evaluation/dispatch.py`|4領域の公平巡回・持回り|
|`backend/src/interview_backend/evaluation/events.py`|strictイベントunion・Streams/保存種別照合|
|`backend/src/interview_backend/evaluation/worker.py`|評価とSTARの実行分岐|
|`backend/src/interview_backend/models/internal.py`|互換Dispatch種別と保存State|
|`backend/src/interview_backend/repositories/coaching.py`|既存V2受付内の補助終了|
|`backend/src/interview_backend/repositories/codec.py`|新レコード/キー/TTL/WorkIndex・strict ID|
|`backend/src/interview_backend/repositories/domain.py`|既存正式受付・冪等namespace・配送との接続|
|`backend/src/interview_backend/repositories/memory.py`|新保存型とSTAR_RUNNING候補|
|`backend/src/interview_backend/star_assist/__init__.py`|独立STARパッケージ|
|`backend/src/interview_backend/star_assist/api.py`|補助API・冪等要求hash|
|`backend/src/interview_backend/star_assist/models.py`|strict契約・独立保存レコード|
|`backend/src/interview_backend/star_assist/provider.py`|専用Fake・事実整合検証|
|`backend/src/interview_backend/star_assist/repository.py`|原子的保存・CAS・期限・quota・反映・終了・Recovery|
|`backend/src/interview_backend/star_assist/storage.py`|状態・終端・receipt整合|
|`backend/src/interview_backend/star_assist/worker.py`|1回呼出し・不明結果/保存確認|
|`backend/tests/unit/test_backend_review_fixes.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_coaching_v2.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_durable.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_dynamodb.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_operational_logs.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_p3_completion.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_question_management.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`backend/tests/unit/test_star_assist.py`|所有者・期限・CAS・受付/配送/Recovery・SDK Stubber回帰|
|`contracts/star-v14-fixtures.json`|カテゴリ/Unicode/hash/UUID/Fake結果の共有fixture|
|`docs/FRONTEND_API_CONTRACT.md`|基準監査・設計・検証結果・配備前承認/既存API契約追記|
|`docs/STAR_V14_BASELINE_AUDIT.md`|基準監査・設計・検証結果・配備前承認/既存API契約追記|
|`docs/STAR_V14_DEPLOYMENT_APPROVAL_REQUIRED.md`|基準監査・設計・検証結果・配備前承認/既存API契約追記|
|`docs/STAR_V14_DESIGN.md`|基準監査・設計・検証結果・配備前承認/既存API契約追記|
|`docs/STAR_V14_OFFLINE_VERIFICATION.md`|基準監査・設計・検証結果・配備前承認/既存API契約追記|
|`frontend/.storybook/preview.tsx`|transactionによるStory seed|
|`frontend/next.config.ts`|独立worktreeの既存依存共有とローカル検証設定|
|`frontend/src/features/feedback/components/organisms/CoachingResponse.tsx`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/components/organisms/AnswerSubmission.tsx`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/components/pages/InterviewPractice.tsx`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/components/pages/PracticeSessionContent.tsx`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/hooks/usePracticeController.ts`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/hooks/usePracticeSession.ts`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/interview/model/practice.ts`|既存画面/ControllerへのSTAR保存・前回回答/クリア操作接続|
|`frontend/src/features/starAssist/components/molecules/StarFields.tsx`|3案編集・明示反映・保存競合・結果不明復旧|
|`frontend/src/features/starAssist/components/organisms/StarAssistPanel.tsx`|3案編集・明示反映・保存競合・結果不明復旧|
|`frontend/src/features/starAssist/hooks/useStarWorkspace.ts`|3案編集・明示反映・保存競合・結果不明復旧|
|`frontend/src/hooks/useAnswerOperation.ts`|pending優先・サーバー復元・再挑戦初回回答・補助参照|
|`frontend/src/lib/api/client.ts`|PUT・strict DTO/client・任意補助ヘッダー|
|`frontend/src/lib/api/interview.ts`|PUT・strict DTO/client・任意補助ヘッダー|
|`frontend/src/lib/api/schemas/star.ts`|PUT・strict DTO/client・任意補助ヘッダー|
|`frontend/src/lib/api/star.ts`|PUT・strict DTO/client・任意補助ヘッダー|
|`frontend/src/lib/jsonHash.ts`|Pythonと一致するcanonical/SHA/UUIDv5|
|`frontend/src/lib/storage/recovery.ts`|旧v1/v2互換と新v3固定Body/補助参照/cache文脈|
|`frontend/src/mocks/browser.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/src/mocks/handlers/index.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/src/mocks/star.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/src/mocks/starHash.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/src/mocks/store/index.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/src/mocks/transactions.ts`|共有Mock V4 transaction・純粋状態・期限/quota・旧版移行|
|`frontend/stories/fixtures/index.ts`|STAR Story受入・既存seed補完|
|`frontend/stories/pages/interview/StarAssist.stories.tsx`|STAR Story受入・既存seed補完|
|`frontend/tests/e2e/coaching-v2.spec.ts`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/tests/e2e/practice.spec.ts`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/tests/e2e/question-management.spec.ts`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/tests/e2e/star-assist.spec.ts`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/tests/review-fixes.test.tsx`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/tests/star-assist.test.ts`|STAR/CAS/移行/復旧/2タブ/画面の受入と旧回帰|
|`frontend/vitest.config.ts`|独立worktreeの既存依存共有とローカル検証設定|
|`terraform/modules/service/auth.tf`|配備候補のみ: JWTルート・CORS・IAM・既定無効TTL・mock検証|
|`terraform/modules/service/data.tf`|配備候補のみ: JWTルート・CORS・IAM・既定無効TTL・mock検証|
|`terraform/modules/service/iam.tf`|配備候補のみ: JWTルート・CORS・IAM・既定無効TTL・mock検証|
|`terraform/modules/service/tests/contract.tftest.hcl`|配備候補のみ: JWTルート・CORS・IAM・既定無効TTL・mock検証|
|`terraform/modules/service/variables.tf`|配備候補のみ: JWTルート・CORS・IAM・既定無効TTL・mock検証|

## 保全・証跡・承認境界

独立worktreeで作業し、元Windows作業ツリーの変更、private証跡、正式Artifact、saved Plan、journal、Draft PR #5を保持した。専用台帳と既存証跡indexを再照合し一致した。検証結果JSONとログ/画像のSHA-256 indexは `.p4-artifacts/star-assist-v14-offline-20261010` 内に保存する。privateログ/状態/正式Artifactをcommitしない。

AWS接続、State操作、remote Plan、Apply/Destroy、Artifact upload、Lambda配備、実OpenAI、main merge、dev有効化を実行していない。将来の配備には対象HEAD、Account/Region、費用上限、saved Plan SHA、資源差分と条件付き自動Closureを固定した別承認が必要。[基準監査](STAR_V14_BASELINE_AUDIT.md) / [設計](STAR_V14_DESIGN.md) / [承認事項](STAR_V14_DEPLOYMENT_APPROVAL_REQUIRED.md)。
