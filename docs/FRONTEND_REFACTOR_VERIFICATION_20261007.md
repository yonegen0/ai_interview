# Frontendリファクタリング検証記録（2026-10-07 / Asia/Tokyo）

既存の未コミットFrontend実装を引き継ぎ、利用者切替・遅延応答・保存失敗・旧Mock要求の安全性をレビューした。commit・push・AWS接続・配備・再有効化は実施していない。API契約、Backend、Terraform、依存パッケージは変更していない。

## 実装構成

- 依存方向は `app → Feature Page → Template → Organism → Molecule → Atom`。管理者・ログイン・練習開始・回答・結果の通信、保存、要求復旧、遷移をhooksへ分離。計算・入力検証・復旧モデルはmodelと既存API Schemaで扱う。
- 管理者画面は `useQuestionBankEditor` と `useQuestionManagement`、表示はQuestionManagementTemplateと編集・競合・プレビュー・保存確認の部品へ分割。
- ログインは `useEmailOtpLogin`、練習は `usePracticeStart`、`usePracticeSession`、`usePracticeController` と既存 `useAnswer`、結果は `useFeedbackResult`、`useFeedbackNavigation` で制御。
- 共通Input・Select・ChoiceButton・Text・Panel・Actions・Header・AppShellを使用。RHF Controllerへのref・blur・値接続を保持。MUI styledとthemeを使用し、src／storiesのsx・React.FC・any禁止項目は検索で該当なし。
- QuestionEditorCardの文字数表示とカテゴリ浮動ラベルの間隔、EmailOtpFormの説明文との間隔を保持。
- 表示Storyはprops／フォームHarness、Page Storyは実hooks＋MSW。認証・Router・Query・Storage・メモリ退避をStoryごとに初期化し、ブラウザー試験を直列実行。

## 安全性レビューと回帰試験

引き継ぎ時点で `tests/review-fixes.test.tsx` に正式回帰試験が存在した。これを保持して、次の5件を追加した。`review-probes.tmp.test.tsx` は開始時点で存在せず、削除・上書きしていない。`*.tmp.test.ts(x)` の除外は旧不具合の再現を期待する一時試験に限定し、正式回帰試験を実行している。

| 確認対象 | 維持・修正した動作 |
| --- | --- |
| 遅延401・本文解析・再ログイン | API要求開始時のscopeと認証generationを検査。他利用者へ本文を再送せず、新ログインをinvalidateしない。同一ログインの401再確認は最初に固定した本文と冪等キーを使用。 |
| 保存の書込み失敗・削除失敗 | dirtyキーはメモリの最新値を優先。削除失敗のtombstoneで古いディスク値を復活させない。利用者へ束縛した保存関数を使用。 |
| Mock質問一覧の容量不足 | 最新bankと要求receiptをメモリに保持し、古い保存値へ戻さない。 |
| 管理者の古いCache | fresh GET成功後に復旧データを比較。保存成功時にCacheも更新し、再マウント後の誤競合を防止。 |
| 遅延開始・回答・次問 | アンマウント／利用者変更後の保存削除、Cache更新、画面遷移を遮断し、元要求を保持。Mutation開始時にも元ログインを確認。 |
| Mock v1移行 | 旧requestsと元v1データを保持し、mock-userへの成功receiptをコピー。開始・回答・次問を再実行せず再確認。移行済v2の旧キーも補完。 |
| 遅延評価・終了操作 | usePracticeControllerのisActiveガードを確認。アンマウント、別利用者切替、同一利用者再ログインの3試験を追加し、遷移と現在の下書き削除が発生しないことを検証。 |
| Query Cache消去と新Query | useAccountActionsを認証変更の同期通知で消去する方式へ変更。React effectで遅れて新利用者のCacheまで消す競合を防止。別利用者／同一利用者の2試験を追加。token refreshではgenerationが変わらずCacheを保持。 |

useEvaluationのscope宣言、useAnswerの保存import・effect依存、AuthBoundaryのscope＋generationによる再マウントを確認。同一ログインのtoken更新では下書きを保持する。保存確認、結果不明の同一要求再確認、競合、401／403、旧Session互換は正式unitとPage Storyで検証する。

## 最終検証

作業ディレクトリはfrontend。以前のログを最終結果として流用せず、今回のログは `.p4-artifacts/frontend-refactor/*-final.log` に保存する。

| コマンド | 最終結果 | 今回のログ |
| --- | --- | --- |
| `npm run lint` | PASS、終了コード0 | `lint-final.log` |
| `npm run typecheck` | PASS、終了コード0 | `typecheck-final.log` |
| `npm run test:unit` | 14ファイル、208件PASS、終了コード0 | `unit-final.log` |
| `npx vitest run --project storybook` | 44ファイル、373件PASS、終了コード0 | `storybook-final.log` |
| `npm run build` | 本番静的build成功、終了コード0 | `build-production-final.log` |
| `npm run build:mock` | Mock静的build成功、終了コード0 | `build-mock-final.log` |
| `npm run build-storybook` | Storybook静的build成功、終了コード0 | `build-storybook-final.log` |
| `npm run test:e2e` | 13件PASS、終了コード0 | `e2e-final.log` |

unitとStorybook、本番とMock buildはそれぞれ順番に実行。通常sandboxのunit開始はVite子プロセスの `spawn EPERM` で失敗したため、ローカル試験・buildは権限昇格して実行した。表は再実行後の最終結果。本番 `out/mockServiceWorker.js` は存在せず、Mock `out-mock/mockServiceWorker.js` は存在する。

非失敗の警告として、Viteの将来native config loaderに対するESM設定警告、Storybook上の画像LCP読み込み警告、Storybook bundleの500kB超とplugin実行時間、E2EのNO_COLOR／FORCE_COLOR警告が残る。依存更新や警告の抑制は行っていない。

## 画面画像

最新Mock buildに対するE2Eで `frontend/playwright/.cache/question-management/` の管理者・練習画像を再生成。375／768／1280pxの各画面についてfullPageとviewportを保存した（計12画像）。6枚のviewport画像を目視確認し、文字数表示とカテゴリ浮動ラベルの間隔、質問改行、入力欄、操作ボタンを確認。3幅ともE2Eの横overflow検査はPASS。管理者の追加・削除・並べ替え・保存、新規練習への反映、既存練習の質問保持、一般利用者のアクセス拒否もPASS。

## SHA-256と差分保持

検証対象のFrontendファイル193件（既存未コミット・未追跡の実装、試験、Story、設定、public資産、READMEを含む）を [frontend-final-source.sha256](../.p4-artifacts/frontend-refactor/frontend-final-source.sha256) で固定した。manifestのSHA-256は `868910b21e860053a7c4e8739996f510ea820f1cb2a59ecfb1fccba67c6755e1`。最終コードでunit、Storybook、lint、typecheckを実行して以降、実装・試験・Storyは変更していない。buildとE2E後もmanifestと現ファイルの一致を確認済み。

各コマンドの結果・終了コード・対象manifest・ログSHA-256・再生成画像SHA-256は [verification-final.json](../.p4-artifacts/frontend-refactor/verification-final.json) に対応づけた。

`git diff -- backend terraform contracts .github README.md docs/FRONTEND_API_CONTRACT.md` のSHA-256は引き継ぎの `outside-before.sha256`、今回開始時、終了時とも `cbf848592ab80f605661583bc83c237d59f2935800db872b1ddfa2480e47383a`。これらの既存差分を保持した。依存ファイルも開始・終了時で同一：

- `frontend/package.json`: `b7f2cd4c12602a8624ac64c6e99150bcc4d6113f2a22340bfcb35aa64044bd5b`
- `frontend/package-lock.json`: `69c63376fb4c003a52c2de2cafa161998c3050bb6133a5c181cbf6727801fa2d`

## Story移行

44 Storyファイル、373 named exports。旧 `Components/Templates/PracticeForm` の23 Storyは `Pages/Interview/PracticeSession` に全件保持。対応は `.p4-artifacts/frontend-refactor/story-migration.json`、現在の件数は `story-counts-final.json`、部品coverageの対応は `story-coverage.json` を参照。

## 未実施事項

実AWSでの配備、実API接続、Cognito EMAIL_OTPの実メール受信、SNS inbox確認、再有効化、実負荷試験は未実施。MockのOTP確認は実OTP検証を意味しない。既存の性能Gate FAIL／`POST_DEPLOY_PERFORMANCE_VALIDATION_REQUIRED` は変更していない。
