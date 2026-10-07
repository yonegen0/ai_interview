# Frontendデザイン・Storybookパス修正（2026-10-07 / Asia/Tokyo）

承認された計画に従い、セージ色・半透明・柔らかい影を維持してデザインとStorybookの配置を修正した。既存未コミット差分を保持し、commit・push・AWS接続・配備・再有効化は実施していない。

## 実装

- InputとSelectの装飾を `src/theme/fieldStyles.ts` に集約。disabledを優先し、errorはfocus・hoverより優先する。エラー中の枠・ラベル・フォーカスの影は赤、修正後のフォーカスは緑。props・RHF・ID・ARIA接続は維持した。
- Buttonの既定variant=textとpropsを維持。主要操作はcontained/primary、補助操作はoutlined/primary、削除・取り消しはoutlined/error、終了の確定はcontained/error、終了確認を開く操作・ログアウトはtext/inherit。Button自身がキーボードのフォーカス枠を持ち、Portalでも表示する。ChoiceButtonの選択状態は維持した。
- 終了確認の説明はinterviewのmodelの純粋関数 `exitNotice` でphaseから選ぶ。下書き破棄、送信中・結果不明の要求保持、評価継続、失敗後の画面退出を区別した。既存の保存・破棄・遷移callbackは変更していない。
- 固定768pxのmedia queryをthemeのmd=900pxへ統一。sm=600pxの狭幅調整は維持。一般的な文字は共通Text・theme.typographyへ、通常余白はtheme.spacingへ、角丸はtheme.shapeからの比率へ集約。h2は小画面18px／広い画面21px。Hero=32px／44px、スコア=48px／64pxはtheme配下の専用トークンで維持した。
- Storyは共通部品 `Components/<層>/<Component名>`、Feature部品 `Components/<層>/<Feature>/<Component名>`、Page `Pages/<Feature>/<画面名>` に統一。実ファイルも同じ分類へ配置した。10組のパス・titleを変更し、相対importとREADMEの現役参照を更新。探索globと直列実行設定は維持した。

## Story移行

変更前は44ファイル・373 Story。全既存exportを保持し、入力の状態優先順位・Buttonの強弱・終了確認の各状態とPortalフォーカスの11 Storyを追加して、44ファイル・384 Storyとなった。`Pages/Interview/PracticeSession` の既存23 Storyは保持した。

- [移行前Story一覧](../.p4-artifacts/frontend-design-fixes/stories-before.json)
- [ファイル・title移行表](../.p4-artifacts/frontend-design-fixes/story-path-migration.json)
- [Story ID・importPath対応表](../.p4-artifacts/frontend-design-fixes/story-id-migration.json)
- [build後のStory index監査](../.p4-artifacts/frontend-design-fixes/story-index-audit.json)

過去のStory index・ログ・画像・検証記録は保存したまま。READMEの現役リンクを新階層へ更新した。title変更でURLのStory IDも変わるため、旧→新対応表を参照する。

## 検証結果

以下は補助操作の最終修正を含むコードでの結果。作業ディレクトリはfrontend、全コマンドの終了コードは0。

| コマンド | 結果 | 今回の最終ログ |
| --- | --- | --- |
| `npm run lint` | PASS | `lint-final.log` |
| `npm run typecheck` | PASS | `typecheck-final.log` |
| `npm run test:unit` | 14ファイル・224件PASS | `unit-final.log` |
| `npx vitest run --project storybook` | 44ファイル・384件PASS | `storybook-final.log` |
| `npm run build` | 本番静的build成功 | `build-production-final.log` |
| `npm run build:mock` | Mock静的build成功 | `build-mock-final.log` |
| `npm run build-storybook` | Storybook静的build成功 | `build-storybook-final.log` |
| `npm run test:e2e` | 22件PASS | `e2e-final.log` |

unitとStorybook、本番とMock buildはそれぞれ順番に実行した。必要なローカル試験・buildはWindows sandboxの子プロセス制限を回避するため権限昇格して実行した。実AWSへは接続していない。

### 表示・操作

- 入力のerror＋focus＋hover、修正後の正常色、disabled＋error優先、RHFのフォーカスとARIA接続をStoryで検証。
- Buttonの主要・補助・危険操作、Portal内のキーボードフォーカス、ChoiceButtonの選択・disabledを検証。28箇所のButton利用を監査し、補助操作と危険操作の指定を確認。
- 終了確認の6 phaseの説明と保持用リンクをStoryで確認。E2EではEscapeで下書きを保持し、終了確定で破棄すること、結果不明の要求を保持して元の練習で再確認できることを検証。
- 375／768／899／900／1280pxで管理者、Home、ログインエラー、練習開始、回答エラー、終了Dialog、結果、ErrorViewを検証。899pxと900pxの文字・マスコットのサイズ切替もCSS値で確認した。
- 55画像を再生成した。各幅の代表画像を目視確認し、並べ替えの緑枠、削除の赤枠、入力エラーの赤い枠・ラベル、結果の改行、900px境界の切替に問題を認めなかった。E2Eでは個々の文字・操作要素のviewport外へのはみ出しを検査した。

### Story indexと差分保持

build後の監査はPASS。既存373 Storyすべてを保持し、94件のStory IDが新titleへ変更された。旧PracticeSessionの23 Storyは保持し、ID重複0・未解決importPath 0。Storyファイル配置とtitleも全件確認した。

保護対象163ファイルとFrontend外の既存diffは開始時から不変。以前の検証で保存した12画像もSHA-256一致を確認した。依存ファイル、API・認証・保存・各Featureのhooks・Mockを変更していない。

### 検証中の修正と警告

最初のStorybook実行では、追加した終了確認5 StoryがDialogのフェード完了前に可視性を判定して失敗した。表示完了を待つよう修正し、対象14件と全384件の再実行に成功。初回の画像確認で並べ替えのButton指定漏れを見つけ、全利用箇所の監査で質問追加・コード再送も補助操作へ修正した。最終コードで全検証を再実行した。初回ログと55画像は別途保持し、最終成功結果と混同しない。

非失敗の警告として、Viteの将来native config loaderに対するESM設定警告、画像LCP読み込み警告、Storybook bundleの500kB超・plugin時間、E2EのNO_COLOR／FORCE_COLOR警告が残る。依存更新や警告抑制は行っていない。

## 証跡と境界

今回のログは `.p4-artifacts/frontend-design-fixes/`、今回の画像は `frontend/playwright/.cache/frontend-design-fixes/` に保存した。旧 `question-management` の画像は上書きしていない。指定漏れ修正前の55画像は `frontend-design-fixes-first-pass/` に保存した。

最終対象ファイル196件は [source-final.sha256](../.p4-artifacts/frontend-design-fixes/source-final.sha256) で固定した。manifestのSHA-256は `2db35fdfe1597e76d4d8e4561fa0f4a8facd649043a6499765e224266510a042`。検証後も全ファイルの一致を確認。最終ログ・画像・移行表・検証結果は [verification-final.json](../.p4-artifacts/frontend-design-fixes/verification-final.json) に対応づけた。

Frontend外のdiff SHA-256は開始・終了とも `cbf848592ab80f605661583bc83c237d59f2935800db872b1ddfa2480e47383a`。依存ファイルのSHA-256は以下のとおりで、開始時から不変。

- `package.json`: `b7f2cd4c12602a8624ac64c6e99150bcc4d6113f2a22340bfcb35aa64044bd5b`
- `package-lock.json`: `69c63376fb4c003a52c2de2cafa161998c3050bb6133a5c181cbf6727801fa2d`

API契約、API client、認証、利用者分離、要求復旧、各Featureのhooks、Mock、Backend、Terraform、依存ファイルを保護対象として開始時のSHA-256を保存した。終了時に比較し、他作業の差分があっても戻さない。

実AWS配備、実API接続、実EMAIL_OTPの受信、SNS inbox確認、再有効化、実負荷試験は未実施。既存の性能Gate FAIL／`POST_DEPLOY_PERFORMANCE_VALIDATION_REQUIRED` は変更していない。
