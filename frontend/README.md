# Interview Pocket Frontend

Backendなしで動く面接練習MVPです。認証・実AI評価は含まず、MSWが固定サンプルを返します。

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

`npm run storybook` で <http://localhost:6006> を開きます。StoryはAtomic Designに合わせた `Components/Atoms`、`Components/Molecules`、`Components/Organisms`、`Components/Templates`と、画面Containerの`Pages/Home`、`Pages/Interview`、`Pages/Feedback`に分類されています。トップ画面からカテゴリ選択、回答、評価待機、結果、再挑戦、次の質問までを個別に開けます。

Feature Storyは実API ClientとMSWを通ります。各Storyの `parameters` で `initialRoute`、固定Repositoryデータ、`pocket:*` の復旧データ、`mockScenario` を指定し、描画前にQuery Cache・Router・対象Storage・Handlerを初期化します。利用できるシナリオは `success`、`slow`、`never`、`validation`、`unauthorized`、`not_found`、`server_error`、`network_error`、`response_lost`、`invalid_response`、`evaluation_failed`、`state_conflict` です。

Storybookブラウザテストは `npm test` に含まれます。Keyboard、Focus、a11y、長文、375／768／1280px、二重操作防止と復旧導線を確認し、静的Storybookは `npm run build-storybook` で生成します。

## マスコット画像

結果・再挑戦・送信中・評価待ち・エラーは共通Molecule `src/components/molecules/MascotCoachCard.tsx` を使用します。見出し・本文・操作を同じカードにまとめ、768px未満では本文と操作を全幅に表示します。画像はstandardで96／144px、結果のfeaturedで112／176pxです。配色はneutral／attention／errorの3種類で、状態判定・文言・ライブ通知は各利用側が管理します。ErrorViewはerror配色を使用し、淡い赤の背景（6%）、赤い枠（30%）、赤い背面の円（10%）と赤い見出しでエラー状態を示します。評価失敗など既存のattention配色は維持します。

ErrorViewの本文は`error.dark`を10%暗くし、AppShellの背景グラデーション上でも読みやすさを保ちます。赤配色の検証では375／768／1280pxの通常・長文・retryなしの9画面で、実際の背景ピクセルに対する見出し・本文のコントラストが4.82:1以上であることを確認しました。画像失敗時の領域維持とキーボード操作も確認済みです。結果と画像はGit管理外の`playwright/.cache/error-color-visual/`に保存しています。

`heading`・`children`・`actions`に表示内容を渡し、任意のスロットを省略すると空の行も省略されます。`Components/Molecules/MascotCoachCard`のStoryで長文、操作なし、スマホ幅、画像失敗を確認できます。カードの外側の余白は利用側で指定します。通常の回答入力中と練習開始画面は従来の表示です。

導入時の検証では、lint・型チェック、232件のテスト（`npm test -- --testTimeout=15000`）、Storybook・本番・Mockの各ビルド、専用の新規Mockサーバーを使った8件のE2Eが成功しています。375／768／1280pxで単体とAppShell内の42画面を確認しました。画面例は`Components/Organisms/ErrorView`、`Components/Organisms/EvaluationLoading`、`Components/Templates/PracticeForm`、`Pages/Feedback/FeedbackResult`の`InAppShell`系Storyから再現できます。

`src/components/atoms/MascotCharacter.tsx` が6種類の装飾画像を表示します。開始画面はwelcome、送信・評価中はthinking、結果見出しはsuccess、有効な再挑戦リンクはretry、共通エラーと評価失敗はerrorです。通常の回答入力中には表示しません。

元画像は `public/images/mascot/mascot-*.png`（1254×1254px、透過付き）に保存し、配信には同名のWebP（512×512px、品質90、アルファ品質100）を使います。元PNGは変更しません。WebPは約48〜62KBで、元PNGより約97%軽量です。静的書き出しに対応するため `next/image` に `unoptimized` を指定し、画像変換サーバーは使用しません。画像読み込み失敗時は装飾だけを隠し、寸法・説明・操作を維持します。

再生成は `frontend` で以下を実行します。既存のNext.js依存に含まれるSharpを使用し、通常のビルド中には画像変換しません。生成したWebPもリポジトリへ含めます。

```powershell
@'
const sharp = require('sharp');
(async () => {
  for (const variant of ['default', 'welcome', 'thinking', 'success', 'retry', 'error']) {
    const base = `public/images/mascot/mascot-${variant}`;
    await sharp(`${base}.png`)
      .resize(512, 512, { fit: 'inside', withoutEnlargement: true })
      .webp({ quality: 90, alphaQuality: 100 })
      .toFile(`${base}.webp`);
  }
})();
'@ | node
```

Storybookの `Components/Atoms/MascotCharacter` で表情・サイズ・取得失敗を、`Components/Templates/PracticeForm` のSubmitting／RetryAfterEvaluationFailureで送信と再入力を確認できます。

## ルート

- / : 入口
- /practice/ : カテゴリ選択
- /practice/session/?sessionId=UUID : 回答と評価待機
- /result/?attemptId=UUID : 結果

再挑戦時はmode=retryとfromAttemptIdを付けます。回答は1〜2000文字。評価GETは2秒間隔、120秒で手動確認に切り替わります。

## 資料

- [API契約](../docs/FRONTEND_API_CONTRACT.md)
- [設計差分ADR](../docs/ADR-001-frontend-standalone-v2.md)
- [リポジトリ案内](../REPOSITORY_GUIDE.md)

Mockのシナリオ切替・実Backendに必要な実装はAPI契約を参照してください。

## Component構成

共通UIは`src/components/`、Feature固有UIは`src/features/<feature>/components/`でAtomic Design階層へ分けています。トップ画面は`src/features/home/components/pages/HomePage.tsx`にあり、Route Entryから描画します。画面遷移には下線付きリンクとブランド用テキスト型を備えた共通`Link` Atomを利用します。依存方向は`Page → Template → Organism → Molecule → Atom`です。下位層から上位層への参照、共通ComponentからFeatureへの参照、Feature間の内部Component参照は行いません。
