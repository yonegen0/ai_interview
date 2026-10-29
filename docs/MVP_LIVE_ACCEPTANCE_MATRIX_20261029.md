# MVP公開受入マトリクス（2026-10-29）

## 目的と証拠の区別

この文書は、Gate B復旧と並行してFrontend/Backendの公開受入項目を一か所に整理した**実行前のチェックリスト**。AWS読取り、IAM変更、Terraform Plan/Apply、enablement、実モデル推論、配備の承認を与えるものではない。Mock/CI/ソースの正常性と、実Cognito・実DynamoDB・実Bedrock・実CloudFrontのPASSを混同しない。

確認したソース（作成時のmain `ec2e8f4daee1dfcd76a3a0119de5585ad99460cf`）：
- [Frontend認証](../frontend/src/lib/auth/session.ts)、[API Client](../frontend/src/lib/api/client.ts)、[STAR Hook](../frontend/src/features/starAssist/hooks/useStarWorkspace.ts)、[API契約](FRONTEND_API_CONTRACT.md)
- [API Lambda](../backend/src/interview_backend/aws_runtime.py)、[API Handler](../backend/src/interview_backend/api/handler.py)、[Cognito/API Gateway設定](../terraform/modules/service/auth.tf)
- [Web root](../terraform/environments/web/main.tf)、[Frontend hosting module](../terraform/modules/frontend/main.tf)、[配備・アップロードRunbook](../terraform/environments/web/README.md)
- [STAR実AIの品質ケース・上限](STAR_V14_LIVE_ADAPTER.md)、[正式性能解析](P4_DEV_PERFORMANCE_ANALYSIS_20261006.md)、[一時検証/Closure承認契約](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)

2026-10-29時点で確認したGitHub差分は、[PR #78](https://github.com/yonegen0/ai_interview/pull/78)のState15復旧ソースmerge、[PR #61](https://github.com/yonegen0/ai_interview/pull/61)のSTAR入力競合修正候補。実AWSのStage復旧成功、実モデル品質、Web配備、公開可能性は本資料の作成では確認していない。後続の運用証拠で更新する。

## 実行順と受入基準

| Gate | 担当 | 実施する検証 | 合格のための実証 |
| --- | --- | --- | --- |
| 0. Stage復旧 | Codex | 最新Sourceに一致する限定IAM/State15/Stage復旧（旧Apply010を再利用しない） | 正規Plan/Applyの正常終了、Stage6項目、State/実Stage整合、全77資源監査、lockなし、4入口閉鎖、readiness false、独立読戻し |
| 1. Backend配備 | Codex | 採用commit/locked Linux Artifact/manifest/4 Lambda alias、必要なIAM・DDB・SQS・Cognitoの一致 | CIだけでなく実AWSへの配備とバージョン/alias/実効アクセスを証拠化 |
| 2. 実認証 | Codex実行、ChatGPT解析 | 招待済みの別々の2利用者でEMAIL_OTP、期限切れ/更新、ログアウト、USER/ADMIN | 実JWT issuer/audience/client_id/token_use/subの整合、401は一度だけrefresh、403更新なし、前本人の表示・キャッシュ・操作が残らない |
| 3. 実API・本人分離 | Codex実行、ChatGPT解析 | Session作成、質問、回答202、Evaluation GET、Feedback、再挑戦、次問、質問管理。成功後の同key照合、本文違い409、他本人の閲覧・変更拒否 | Response/HTTP/Zod/Backend契約一致。OWNER AのIDをOWNER Bから取得・更新できない。ADMIN書込みはADMINのみ |
| 4. STAR・Coaching | Codex実行、ChatGPT解析 | 下書き保存/復元、STAR 3案・編集・明示反映、通常送信、Coaching V2 30点・最大3深掘り、結果不明・再送抑制 | 出典違反0、既存12品質ケースに基づく人手評価を記録。生成中編集で新しいメモが消えない。未確定推論の自動再実行0 |
| 5. 非同期信頼性 | Codex実行、ChatGPT解析 | DDB Streams→Dispatcher→SQS→Worker、期限/重複配送/障害/Recovery、DLQ・Usage | 一つの処理権を維持し、同一回答の二重推論・重複使用量計上なし。異常時は停止/回復結果の分類が一致 |
| 6. 30人性能 | Codex計測、ChatGPT解析 | 以前のScenario Cと同じ30人・1秒分散、cold/warm/POST/GETを分離し測定。実モデルの別バッチも計測 | 正式API p95が2,000ms以下、30評価が30秒以内。2026-10-06のp95=2,003.466msはFAILのまま。測定母集団や閾値を後から変更しない |
| 7. Web配信 | Codex配備、ChatGPTレビュー | `frontend/out` のみを非公開S3/OACへ配置、CloudFront、CORS、実URLのリロード・404・MIME・cache・headers | `NEXT_PUBLIC_MSW_ENABLED=false`、公開環境変数だけがHTML/JSへ埋込、Mock worker・source map・token/秘密ファイルなし。ルート/深いURLが動作 |
| 8. 公開・Closure | Codex実行、ChatGPT判定 | SNS/Alarm/予算・実AIトークン/費用、承認済み短時間検証、独立閉鎖。公開切替は別途承認対象 | 未解決の公開阻害P0/P1なし。別途指定した公開条件を満たす。dev一時検証後は成功/失敗にかかわらず許可範囲内で4入口を閉鎖し、実状態を読戻す |

## ChatGPT側がAWSなしで完了できるチェック

- **STAR競合**：PR #61の修正が入力の開始時snapshotを保存前に固定すること、保存中にユーザーが変更した文章が自動採用で上書きされないことを変更差分と回帰テストで確認する。最新mainへの統合と真正必須CIを経て通常mergeする。
- **Frontend API/認証**：`request()` の401単回refresh、403非refresh、JSON/Zod応答、Abort/Timeout、POSTキー/本文維持、画面離脱/本人切替での遅延結果拒否を既存テストと照合する。未カバーの**再現可能な**不具合のみ最小PRで修正する。
- **Backend契約/権限**：Lambda APIのJWT claims guardとOWNER/ADMIN分離、Session/Attempt/Evaluation/STARのAPI契約、409/429/5xx、冪等・Recovery・使用量制限の契約テストを確認する。MockによるPASSを実IAM/DDB保証と書かない。
- **Frontendビルド**：GitHub Actionsでlint、typecheck、`npm test`、`npm run build`、`npm run build-storybook`、`npm run build:mock`、`npm run test:e2e` と依存auditを確認する。実ブラウザでのAPI接続は別。
- **Hostingの事前監査**：`terraform/modules/frontend`には非公開S3/CloudFront OAC/CloudFront Function、`terraform/environments/web`には独立State rootがある。旧[インフラ概要](INFRASTRUCTURE_OVERVIEW.md)の「hosting未定義」は作成時点の記録なので、現在の未配備証拠として流用しない。
- **性能調査**：`aws_runtime.build_entry`の初回設定・質問読込・DDB client構築と、APIに不要なimportを測定対象にする。不要な機能削除・閾値変更・PC常時課金を先行させない。

## Codex実行時に保存する最小結果

各Gateごとに **結果 (PASS/FAIL/NOT_RUN)**、対象source SHA、Artifact/Frontend build digest、Account/Region・AWS aliasまたはCloudFront distributionのprivate識別、実行した操作数、費用/usage、HTTP/HTTP APIとLambdaの相関、実測p95/30件時間、失敗reason、AWS閉鎖後のreadbackを記録する。個人の回答本文、JWT、OTP、秘密鍵、raw機密logは公開PR/Actions artifactへ保存しない。

**停止条件**：未知のState/lock、差分の逸脱、結果不明Apply、実モデルへの想定外送信、本人分離失敗、費用上限の不確実性、未承認AWS変更。失敗Apply/推論を新しいkeyで自動再試行しない。承認済みClosureが適用可能な正常Stateならその既存契約を優先する。

## 公式資料

- [Next.js Static Export](https://nextjs.org/docs/app/guides/static-exports)
- [Next.js公開環境変数](https://nextjs.org/docs/app/guides/environment-variables)
- [AWS CloudFront S3 OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [Amazon Cognito authentication](https://docs.aws.amazon.com/cognito/latest/developerguide/authentication-implement.html)
- [AWS HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [AWS Lambda lifecycle](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)
