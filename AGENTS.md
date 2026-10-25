# ai_interview 開発ルール

## 1. 禁止事項
- `main` への直接push、force push、GitHub Rulesetの迂回、未承認の保護変更・branch削除を禁止する。
- AWSへの接続・読取り、GitHub上の高リスク操作、配備、実AI有料推論は既存の承認・権限境界に従う。
- Terraform `init` / `plan` / `apply`、State読取り・変更は安全なオフライン検証と混同せず、Runbookの実行条件を守る。
- 消費済み・期限切れ・対象SHA不一致の承認を再利用せず、承認範囲・回数・費用・操作対象を無断で拡大しない。
- Secrets、資格情報、State、saved Plan、private ledger・監査証跡の漏洩・無断上書きを禁止する。
- Git履歴・未コミット変更・既存機能・契約・互換性を無断で破壊しない。
- Mock/Fake/CI成功を、実AWS・実AI・実効IAMの成功として報告しない。

## 2. プロジェクト概要・開発方針
- 最大30人向けのAI面接練習Webアプリ。FrontendはNext.js/React/TypeScript、BackendはPython/Lambda、InfrastructureはTerraform/AWS。
- 完全サーバーレス、AWS無料枠優先・低固定費、最小権限、本人別データ分離、冪等性・Recoveryを重視する。
- Coaching V2、STARアシスト、V1互換、認証、質問管理、非同期評価と既存API契約を保持する。
- AIの採用方針はBedrock Claude Haiku 5.5（JP Geo）を標準、OpenAIを手動切替の予備とし、自動フォールバックしない。採用方針と配備状態を区別する。
- 許可範囲の調査→最小修正→検証→セルフレビューは自律的に進め、高リスク境界でのみ停止する。
- 実装・ローカルMock/Fake・CI・実AWS/実AI検証の事実を明確に区別する。
- 依存・実装の採用バージョンを先に確認し、外部仕様に関わる変更では対応する最新の公式資料を優先する。無根拠の依存更新はしない。

## 3. 詳細方針・コーディング規約
- 対象ディレクトリの規約を着手前に確認し、横断変更ではすべての該当規約を読む。下位規約で本ファイルの安全原則を緩和しない。
- [Frontend規約](frontend/AGENTS.md)／[Backend規約](backend/AGENTS.md)／[Terraform・AWS規約](terraform/AGENTS.md)。
- `.github/workflows/` のTerraform・IAM・OIDC・AWS配備関連変更は[Terraform・AWS規約](terraform/AGENTS.md)も参照する。
- 自律判断・main merge条件：[CODEX_AUTONOMY_RULES](docs/CODEX_AUTONOMY_RULES.md)。
- AWS運用・承認・Closure・障害復旧：[P4_TERRAFORM_RUNBOOK](docs/P4_TERRAFORM_RUNBOOK.md)とそこから参照する承認文書。
