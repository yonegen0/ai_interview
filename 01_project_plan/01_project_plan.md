---
document_id: PLAN-001
title: "AI面接練習Webアプリ MVP プロジェクト計画書"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 目的

本プロジェクトは、転職活動中の求職者が通勤・移動中の短い時間でも、
スマートフォンから一問一答形式で面接練習を反復できるWebアプリのMVPを構築する。

最重要価値は「完成された回答を作ること」ではなく、
**質問を見て短時間で考え、言葉にする回数を増やすこと**である。

# 2. 背景・解決する課題

- 突然質問されると言葉に詰まる
- 頭の中では分かっていても即時に言語化できない
- 面接回答の引き出しが少ない
- まとまった面接対策時間を確保しにくい
- 電車内では音声面接が使いづらい
- 長文フィードバックは隙間時間に不向き

# 3. 成功条件

## 3.1 プロダクト成功条件

- 1問の「質問確認 → 回答 → AIフィードバック → 次の質問」がおおむね3分で完結する
- 375px幅程度のスマートフォンでも主要操作が成立する
- AIフィードバックが短く、次の回答改善に直結する
- 未回答質問を優先し、同じ質問ばかり出題されない
- 面接直前にお気に入り回答を素早く復習できる
- 管理者が利用者の練習状況を確認できる

## 3.2 技術成功条件

- 常時稼働サーバーを持たない
- 認証済みかつ`PROFILE.status=ACTIVE`の利用者だけがAI APIを利用できる
- Access Tokenの`token_use=access` / `client_id`をLambdaでも確認する
- USER/ADMINの権限制御がサーバー側で成立する
- 同一論理送信の通信再送では同一`practiceId`を使い、Bedrockの二重実行を抑止する
- `REQUEST`作成と日次AI利用回数加算が原子的に成立する
- AI利用回数をユーザー単位で制御できる
- 回答本文・OTP・JWTを通常ログへ出さない
- dev/prodを分離して再現可能にデプロイできる

# 4. スコープ

## 4.1 MVP対象

- 管理者による求職者登録
- Email OTPログイン
- USER / ADMIN認可
- 7カテゴリ程度のQuestion Bank
- 約100問の一問一答
- テキスト回答
- S/A/B/C評価
- 良かった点
- 改善ポイント
- ブラッシュアップ回答例
- 履歴
- お気に入り
- 管理者ユーザー一覧・詳細
- PWA
- 過去履歴・お気に入りのオフライン閲覧
- 利用制限・監視・コストアラート

## 4.2 MVP対象外

- 音声認識・音声面接
- AIによるリアルタイム質問生成
- Bedrock Agents
- 求人票・職務経歴書との自動連携
- 複雑な分析ダッシュボード
- プッシュ通知
- 完全オフライン同期
- 一般ユーザーのセルフサインアップ
- 決済
- マルチテナントSaaS化

# 5. 体制

現時点では小規模MVPを前提とする。

| 役割 | 主責務 | 備考 |
|---|---|---|
| プロダクトオーナー | 優先順位、受入判断、業務要件 | TBD |
| フルスタック開発 | Frontend / Backend / AWS IaC | 1名中心を想定 |
| 転職支援担当 | Question Bank、評価基準、受入テスト | 業務レビュー |
| テスター | 実機確認、回帰確認 | 兼任可 |

# 6. 開発フェーズ

日付固定ではなく相対週で管理する。人数・稼働率確定後に実日程へ変換する。

| フェーズ | 目安 | 主成果物 |
|---|---:|---|
| P0 要件・設計確定 | W1 | 基本/詳細設計、TBD解消 |
| P1 基盤構築 | W2 | CDK、Cognito、DynamoDB、API skeleton、Static hosting |
| P2 Backendコア | W3 | Question Bank、AI評価、履歴、冪等性、利用制限 |
| P3 Frontendコア | W4 | Login、Practice、Feedback、History、Favorites |
| P4 Admin/PWA | W5 | Admin、IndexedDB、Service Worker |
| P5 結合・品質 | W6 | Story/Vitest/E2E、実機、セキュリティ、負荷確認 |
| P6 パイロット | W7〜 | 少人数試行、改善、MVP受入 |

> 上記は計画用の暫定モデルであり、納期コミットではない。

# 7. マイルストーン

## M1 設計凍結
- 基本設計承認
- 詳細設計のP0項目承認
- Question Bank v1の形式確定
- AI評価Rubric v1確定

## M2 技術疎通
- Email OTPログイン成功
- Access TokenでHTTP API認証成功
- LambdaからDynamoDB読み書き成功
- LambdaからNova 2 Lite呼び出し成功
- S3/CloudFrontからStatic Exportを配信

## M3 USER機能完成
- 1問一答
- AI feedback
- 履歴
- お気に入り

## M4 ADMIN/PWA完成
- ユーザー作成
- 練習状況確認
- オフライン閲覧
- Service Worker更新動作

## M5 MVP受入
- 主要E2E通過
- 実機確認
- コスト/監視確認
- 少人数パイロット可能

# 8. 品質方針

## Frontend
- TypeScript strict
- `any`禁止
- `React.FC`禁止
- Featureから直接`fetch`禁止
- MUI `styled()`を基本とする
- Storybookで主要状態を再現
- 375×667 / 390×844 / 430×932を重点確認

## Backend
- Lambda Handlerを薄くし、ドメインロジックを分離
- Request/Response validation
- AI出力Schema validation
- IAM最小権限
- PIIを通常ログへ出さない
- RetryでAI二重課金が起きにくい設計

## Infrastructure
- CDK v2
- dev/prod分離
- S3 Public Access Block
- CloudFront OAC
- Budget/Alarm
- 変更は原則IaC経由

# 9. リスク管理

| リスク | 影響 | 対応 |
|---|---|---|
| Bedrock応答遅延 | UX悪化 | 短いprompt/output、計測、Cold Start最小化 |
| AI形式崩れ | 画面表示不能 | named Tool Choice + `stopReason=tool_use` + Schema validation |
| AIの事実捏造 | 面接品質/信用低下 | system prompt、評価テスト、入力事実範囲ルール |
| 通信タイムアウト後の二重送信 | Bedrock費用増 | Transport Retryは同一`practiceId`。新しい練習のみ新ID |
| 日次上限と冪等ロックの競合 | 利用回数不整合 | REQUEST作成 + USAGE加算をDynamoDB Transaction化 |
| 停止ユーザーの発行済JWT | 認可逸脱 | PROFILE status gate + AdminDisableUser + AdminUserGlobalSignOut |
| ID Token誤利用 | 認可逸脱 | Lambdaで`token_use=access` / `client_id`を必須検証 |
| OTPメール不達 | ログイン不能 | SES設定/監視、一般化したエラー表示 |
| PWA旧キャッシュ | version不整合 | version管理、SW更新、unsupported response |
| 端末キャッシュの個人情報残留 | 個人情報漏えい | sub分離、30日expiry、logout/startup cleanup、手動削除 |
| XSSによるToken窃取 | セッション悪用 | `sessionStorage`、third-party script最小化、HTML injection禁止、CSP |
| AWS費用暴走 | 高 | 日次上限を主制御、API throttling、reserved concurrency、DynamoDB max throughput、Budget監視 |
| Questionのマンネリ | 継続率低下 | 未回答優先、直近重複回避 |

# 10. 変更管理

重要なアーキテクチャ変更はADRとして残す。

例:
- ADR-001 認証クライアントライブラリ
- ADR-002 Token Storage
- ADR-003 APIをCloudFront経由にするか
- ADR-004 Question Bankの配布方式
- ADR-005 AIモデル変更

# 11. 完了条件

MVP完了は「コードが動く」だけではなく、以下を満たすこと。

- 主要機能が受入条件を満たす
- セキュリティ上のP0指摘が残っていない
- dev/prodデプロイ手順が再現できる
- 監視/アラート/コスト上限が設定されている
- Question Bank v1・Prompt v1がversion管理されている
- 管理者向け最低限の運用手順がある

# 12. 実装前に確定が必要なTBD

- 1ユーザー1日のAI上限
- DynamoDB本体データ保存期間
- 本番ドメイン
- パイロット人数
- AWS Budget閾値
- Lambda Reserved Concurrency

以下はv1.1で設計判断済み:
- Token Storage: Amplify Auth + `sessionStorage`
- IndexedDB: 直近50件目安、最終アクセスから30日で期限切れ
- Transport Retry: 同一`practiceId`
- Question Bank: Git上のCanonical Sourceからbuild生成

---

## 参照公式ドキュメント

- [Amazon Cognito - Authentication flows / Passwordless](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html)
- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)
- [Amazon Bedrock - Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [DynamoDB - On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

