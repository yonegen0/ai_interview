# Interview Pocket Frontend

デフォルト15問の通し・カテゴリ練習、一巡終了、管理者による質問編集を実装しています。
実Cognito EMAIL_OTPログインと実API接続に対応し、MSWではAWS通信なしでサンプル評価を確認できます。
新しい質問管理APIとadmin Lambdaの実AWS配備は後続工程です。

## 質問管理・認証

- `/practice/`：全質問またはカテゴリを選択して練習。
- `/login/`：登録済みメールアドレスのEMAIL_OTP認証。タブ内で維持し、token更新・ログアウトに対応。
- `/admin/questions/`：ADMIN専用の本文・カテゴリ編集、追加、削除、上下移動、確認・保存。
- 保存後の新規練習に反映し、既存練習の質問は保持。競合時は編集を残して最新版と比較。
- Mockの管理者ログインは `admin@example.invalid`、コード `123456`。実認証では使用しません。

実接続では `.env.example` のAPI URL、Cognito Region／User Pool ID／Client IDを設定し、
`NEXT_PUBLIC_MSW_ENABLED=false`とします。公開識別子だけを設定し、AWS credentialは渡しません。
設定不足時にMockへ自動切替しません。
実AI評価と実OTP完了の証明は含めません。
[実装・検証記録](../docs/QUESTION_MANAGEMENT_VERIFICATION_20261006.md)を参照してください。

## 起動

Node.js 22以上。`npm ci` 後に `npm run dev:mock` を実行し、http://localhost:3000 を開いてください。

## 検証

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run build-storybook
npm run build:mock
npm run test:e2e
```

Playwrightブラウザが未導入なら `npx playwright install chromium` を実行します。
通常の本番成果物はout/、Mock静的成果物はout-mock/です。
`node scripts/serve.mjs out-mock` で http://127.0.0.1:4173 に配信できます。
本番用にMockを有効化したビルドは拒否されます。検証時だけbuild:mockを使います。

## Storybook

`npm run storybook` で <http://localhost:6006> を開きます。StoryはAtomic Designに合わせた `Components/Atoms`、`Components/Molecules`、`Components/Organisms`、`Components/Templates`と、画面Containerの`Pages/Home/HomePage`、`Pages/Interview`、`Pages/Feedback`に分類されています。トップ画面からカテゴリ選択、回答、評価待機、結果、再挑戦、次の質問までを個別に開けます。

Feature Storyは実API ClientとMSWを通ります。各Storyの `parameters` で `initialRoute`、固定Repositoryデータ、`pocket:*` の復旧データ、`mockScenario` を指定し、描画前にQuery Cache・Router・対象Storage・Handlerを初期化します。利用できるシナリオは `success`、`slow`、`never`、`validation`、`unauthorized`、`not_found`、`server_error`、`network_error`、`response_lost`、`invalid_response`、`evaluation_failed`、`state_conflict` です。

Storybookブラウザテストは `npm test` に含まれます。Keyboard、Focus、a11y、長文、375／768／1280px、二重操作防止と復旧導線を確認し、静的Storybookは `npm run build-storybook` で生成します。

## マスコット画像

結果・再挑戦・送信中・評価待ち・エラーは共通Molecule `src/components/molecules/MascotCoachCard.tsx` を使用します。見出し・本文・操作を同じカードにまとめ、768px未満では本文と操作を全幅に表示します。画像はstandardで96／144px、結果のfeaturedで112／176pxです。配色はneutral／attention／errorの3種類で、状態判定・文言・ライブ通知は各利用側が管理します。ErrorViewはerror配色を使用し、淡い赤の背景（6%）、赤い枠（30%）、赤い背面の円（10%）と赤い見出しでエラー状態を示します。評価失敗など既存のattention配色は維持します。

ErrorViewの本文は`error.dark`を10%暗くし、AppShellの背景グラデーション上でも読みやすさを保ちます。赤配色の検証では375／768／1280pxの通常・長文・retryなしの9画面で、実際の背景ピクセルに対する見出し・本文のコントラストが4.82:1以上であることを確認しました。画像失敗時の領域維持とキーボード操作も確認済みです。結果と画像はGit管理外の`playwright/.cache/error-color-visual/`に保存しています。

`heading`・`children`・`actions`に表示内容を渡し、任意のスロットを省略すると空の行も省略されます。`Components/Molecules/MascotCoachCard`のStoryで長文、操作なし、スマホ幅、画像失敗を確認できます。カードの外側の余白は利用側で指定します。通常の回答入力中と練習開始画面は従来の表示です。

導入時の検証では、lint・型チェック、232件のテスト（`npm test -- --testTimeout=15000`）、Storybook・本番・Mockの各ビルド、専用の新規Mockサーバーを使った8件のE2Eが成功しています。375／768／1280pxで単体とAppShell内の42画面を確認しました。画面例は`Components/Organisms/ErrorView`、`Components/Organisms/Interview/EvaluationLoading`、`Pages/Interview/PracticeSession`、`Pages/Feedback/FeedbackResult`の`InAppShell`系Storyから再現できます。

`src/components/atoms/MascotCharacter.tsx` が6種類の装飾画像を表示します。開始画面はwelcome、送信・評価中はthinking、結果見出しはsuccess、有効な再挑戦リンクはretry、共通エラーと評価失敗はerrorです。通常の回答入力中には表示しません。

2026-09-22に配信画像を修正しました。従来の`.webp`は実体が1254×1254pxのPNGだったため、元データを同名の`.png`として保全し、512×512pxの実WebPへ再生成しています。E2Eの512px期待値は維持しています。

元画像は `public/images/mascot/mascot-*.png`（1254×1254px、透過付き）に保存し、配信には同名のWebP（512×512px、品質90、アルファ品質100）を使います。元PNGは変更しません。再生成後は53,362〜66,402 bytes（元PNG比約96〜97%軽量）です。静的書き出しに対応するため `next/image` に `unoptimized` を指定し、画像変換サーバーは使用しません。画像読み込み失敗時は装飾だけを隠し、寸法・説明・操作を維持します。

再生成は `frontend` で以下を実行します。既存のNext.js依存に含まれるSharpを使用し、通常のビルド中には画像変換しません。生成したWebPもリポジトリへ含めます。

```powershell
node scripts/build-mascots.mjs
```

Storybookの `Components/Atoms/MascotCharacter` で表情・サイズ・取得失敗を、`Pages/Interview/PracticeSession` のSubmitting／RetryAfterEvaluationFailureで送信と再入力を確認できます。

## ルート

- / : 入口
- /practice/ : 通し・カテゴリ選択
- /practice/session/?sessionId=UUID : 回答と評価待機
- /result/?attemptId=UUID : 結果

再挑戦時はmode=retryとfromAttemptIdを付けます。回答は1〜500文字。評価GETは2秒間隔、120秒で手動確認に切り替わります。

## 資料

- [設計書一覧](../設計書一覧/00_管理/00_設計書一覧.md)
- [現Frontend契約の採用ADR](../docs/ADR-002-frontend-contract-alignment.md)
- [API契約](../docs/FRONTEND_API_CONTRACT.md)
- [設計差分ADR](../docs/ADR-001-frontend-standalone-v2.md)
- [リポジトリ案内](../REPOSITORY_GUIDE.md)

Mockのシナリオ切替・実Backendに必要な実装はAPI契約を参照してください。

## Component構成

共通UIは`src/components/`、Feature固有UIは`src/features/<feature>/components/`でAtomic Design階層へ分けています。トップ画面は`src/features/home/components/pages/HomePage.tsx`にあり、Route Entryから描画します。画面遷移には下線付きリンクとブランド用テキスト型を備えた共通`Link` Atomを利用します。依存方向は`Page → Template → Organism → Molecule → Atom`です。下位層から上位層への参照、共通ComponentからFeatureへの参照、Feature間の内部Component参照は行いません。

## 実API接続準備（設計書v2.1）

今回の実行結果と既知失敗は[検証記録](../docs/FRONTEND_ALIGNMENT_VERIFICATION.md)を参照してください。

現API・復旧・画面を維持し、FORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERRORの日本語表示を追加します。
型・制約はsrc/lib/api/schemas、HTTP・冪等性・復旧はdocs/FRONTEND_API_CONTRACT.mdを正本とします。
認証SDK・Token付与・更新・ログアウトと質問管理の実装は上記の2026-10-06更新を参照してください。
実AWSでの新機能の配備・実機検証は後続工程です。
[Backend着手前の必須事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)を参照してください。

## 2026-10-06 hooks・Atomic Design・Storybook

画面Containerは各Featureのhooksを呼び、`view`（表示状態）、`form`／`editor`（RHF接続）、`actions`（操作）をTemplateへ渡します。Template／Organismは通信・Storage・冪等キー生成を行いません。UI内部のController・useIdなどは表示のために使用します。純粋な計算・戻り先検証・復旧Schemaは各Featureのmodelに置き、API Schemaは引き続きlib/api/schemasを使用します。

管理者画面はeditor hookと保存・復旧hookを組み合わせています。確認対象の質問一覧を独立したスナップショットにし、保存前に期待版・本文・冪等キーを保存します。結果不明の間は同じ要求だけを確認します。質問UUIDとFieldArrayのfieldKeyは別に扱います。認証サービス、API client、保存領域のキー・形式は維持しています。

共通UIはInput／Select／Button／Actions／Panel／Headerに加え、選択状態を表すChoiceButtonと、themeの文字スタイルを使うTextを使用します。新規フォームはControllerで入力本体のref・blur・値を接続します。スタイルはMUI styled、palette・spacing・typography・shape・shadows・breakpointsを使用します。

Storyは次の責務で追加します。

- `Components/Atoms|Molecules|Organisms|Templates`：propsと固定fixtureで表示を確認します。RHF接続はstories/test-utils/presentation.tsxのHarnessで再現し、APIを呼びません。
- `Pages/Admin|Auth|Interview|Feedback`：実際のhooksとAPI clientをMSW／Mock Repositoryへ接続し、操作・復旧・遷移を確認します。
- 旧PracticeFormの通信・復旧・遷移Storyは、削除せず`Pages/Interview/PracticeSession`へ移しました。表示専用の`Components/Templates/Interview/PracticeForm`は別に用意しています。

StoryごとにRouterのpathname・searchParams、Query、認証利用者、Mock Repository、handler、利用者別Storageとメモリ退避を初期化します。`mockRole`はUSER／ADMIN／ANONYMOUSです。管理者Storage fixtureは認証利用者の設定後に保存します。タイマーの60秒経過はunit試験、Storyでは固定待ち時間を確認します。Select／DialogのPortal操作はdocument.bodyを対象にします。

新しい部品を追加する際は、Feature固有か共通かを決め、下位から上位を参照しない層へ置きます。Storyには通常・不正入力・disabledなど必要な状態と重要な操作を追加し、主要画面は375／768／1280pxを確認します。callbackはfn()、API障害はhandlerで再現します。

```powershell
npm run test:unit
npx vitest run --project storybook
npm run build-storybook
```

2026-10-07の最終検証結果・Story移行対応は[リファクタリング検証記録](../docs/FRONTEND_REFACTOR_VERIFICATION_20261007.md)を参照してください。AWS接続・配備・再有効化は実施しません。

## 2026-10-07 デザイン・Storybookパスの統一

共通部品のStoryは `stories/components/<層>/<Component名>.stories.tsx` と `Components/<層>/<Component名>`、Feature部品は `stories/components/<層>/<feature>/<Component名>.stories.tsx` と `Components/<層>/<Feature>/<Component名>` に揃えます。Pageは `stories/pages/<feature>/<画面名>.stories.tsx` と `Pages/<Feature>/<画面名>` です。表示用Harnessを使う場合も、ファイル名とtitleは表示対象のComponent名にします。

`Pages/Interview/PracticeSession` の既存23 Storyは保持しています。Story探索globは変更しません。サイドバーのtitle変更に伴う旧・新Story IDとimportPathの対応は今回の検証証跡に保存します。過去の検証記録・画像は当時のパスのまま保持します。

Buttonは主要操作にcontained、補助操作にoutlined、削除にoutlined/error、終了の確定にcontained/errorを使用します。入力エラーはフォーカス中も赤を維持し、disabledを優先します。画面幅の切替はthemeのmd（900px）です。

[今回の実装・検証記録](../docs/FRONTEND_DESIGN_FIX_VERIFICATION_20261007.md)を参照してください。
