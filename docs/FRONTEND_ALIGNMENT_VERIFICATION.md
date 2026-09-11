# Frontend契約整合 v2.1 検証記録

実行日: 2026-09-11。実行環境: Windows、Node.js v24.14.1、npm 11.11.0。
対象: [ADR-002](ADR-002-frontend-contract-alignment.md)の設計整合とAPIエラー表示。
Runtime要件・CIのNode.js 22設定は変更していない。

## 変更内容

- 設計書一覧の31文書（READMEを含む）を更新。未変更7文書の版は維持。
- [API契約](FRONTEND_API_CONTRACT.md)を正本に、6 Route・202受付とGET・100点評価・全POST冪等キーへ整合。
- Frontend配置・復旧・静的URL、Backend論理モデル・AI業務出力、CORS・CI・次工程の要件を更新。
- 新ADRを追加し、ルートREADME・リポジトリ案内・Frontend READMEから現在の資料へリンク。
- [API Client](../frontend/src/lib/api/client.ts)に4コードの日本語表示を追加。
- [APIテスト](../frontend/tests/api.test.ts)に7ケースを追加。共通Mock Scenarioは変更していない。
- API Schema・Hook・Reducer・保存形式・UI・画像・依存関係は変更していない。

## コマンドと結果

Frontendを作業ディレクトリとして実行した。

| 確認 | 結果 |
|---|---|
| npm run lint | 成功 |
| npm run typecheck | 成功 |
| npm run test:unit -- --testTimeout=15000 | 7ファイル・40件成功 |
| npm test -- --testTimeout=15000 | 最終実行: 26ファイル・245件成功 |
| npm run build | 成功 |
| npm run build:mock | 成功 |
| npm run build-storybook | 成功 |
| npm run test:e2e -- --retries=0 | 7件成功・既知の画像寸法で1件失敗 |
| Markdownの相対リンク確認 | 対象文書のリンク先存在を確認、リンク切れなし |
| git diff --check | 成功 |

E2EはCI=1をコマンド実行環境に設定し、既存サーバーを再利用せず生成済みout-mockを配信した。
失敗を再試行で隠さないためretries=0とした。テストの除外・期待値変更はしていない。
本番・Mockとも /、/_not-found、/practice、/practice/session、/result の静的生成を確認した。

## 新規テストの確認範囲

- FORBIDDEN／RATE_LIMITED／AI_TIMEOUT／AI_UPSTREAM_ERRORの日本語表示。
- 未知コードの汎用表示と、Backendの非公開messageをエラー表示へ露出しないこと。
- 本番と同じQuery設定でMutationを実行し、HTTPエラーでPOSTが自動再送されないこと。
- 403/429と502/504の未確定判定が既存のままであること。
- 502/504後に同じキー・本文で手動確認し、繰り返してもAttemptが1件であること。

既存のHook・契約・統合・Storyテストでも、未確定要求優先、下書き復元、
終端後のタイマー停止、新しい評価IDでの再開などを検証した。

## E2Eと既知問題

成功した7件は通常練習・再挑戦・次問・結果直アクセス・ブラウザ遷移、
応答消失後の重複なし復旧、評価中の再読み込み、下書き復元・不正ID、
375／768／1280pxのレイアウト。

画像テストは [practice.spec.ts](../frontend/tests/e2e/practice.spec.ts) のnaturalWidth確認で失敗した。
期待値512に対して実測1254。Sharpのメタデータ確認でも6種類すべて1254×1254px、
1,672,792〜1,903,163 bytesだった。今回画像を変更していない。
この失敗により、同じE2Eケース内の後続の画像失敗操作は到達していない。
画像失敗後の領域・操作確認は、成功した既存Storyテストでも検証されている。

生成されたPlaywrightレポートはfrontend/playwright-report/、
失敗時のスクリーンショット・traceはfrontend/test-results/にある（Git管理外）。

## 検証中に発生したこと

最初の単体テスト起動はsandboxのspawn EPERMで失敗し、承認経路で再実行して成功した。
全テストの初回は本番ビルドとの同時実行中にMascotCoachCardのImage Load Failure Storyで
画像読込待ちがTimeoutし、244件成功・1件失敗だった。
コード・Story・画像を変えず、ビルドと同時実行しない全テスト再実行では245件成功した。
タイミング依存の可能性があるが、原因の確定はしていない。画像寸法のE2E失敗とは区別する。
Vite設定の将来互換性、Next ImageのLCP、Storybookのchunk sizeに関する非阻害警告も出た。

## 次工程

[決定事項・未確定事項](../設計書一覧/04_横断仕様/06_決定事項_未確定事項.md)に、
非同期起動、受付と起動の整合、重複・期限切れ回復、外部AI完了不明、
物理キー・GSI・Transaction・保持期間、Lambda担当・IAM・監視の必須成果を記載した。
認証接続前にはToken更新、認証切れ、ログアウト時のCache・保存情報処理を確定する。

本記録はMSWによる接続準備の検証であり、認証・実Backend・OpenAI・AWSの検証完了ではない。
既知WebP最適化は別工程。ステージング・コミット・AWS操作・公開は実施していない。
