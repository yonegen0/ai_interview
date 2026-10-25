# AGENTS.md最適化・監査報告（2026-10-19 JST）

## 1. 基準と範囲

- リモート取得：`yonegen0/ai_interview`、`main=ca4d7976e779473b6d0650f9f69484705bdb5798`。
- mainのBackend/Frontend/オフラインP4 CIは直近実行で成功。別の過去Cloud Plan workflowは失敗。PR #19, #20, #21はOpen/Draft、HEADはmainへ未統合。
- 手元のWindows worktree、Git未追跡・未commit差分、Bootstrap Private Ledger/承認情報・実AWS Stateは**未確認**。
- GitHub read-only確認のみ。GitHub書込み、branch/commit/PR、AWS/TF/有料推論操作を一切実行していない。

## 2. 棚卸しと移管

| 原記載元 | 主要内容 | 新しい扱い |
|---|---|---|
| `AGENTS.md` 最初の節 | P4 dev Enablement/Closureの詳細、4update、検証Alarm削除、失敗時停止 | `docs/P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md`を既存の詳細正本として維持。RootではRunbook参照のみに削減 |
| `AGENTS.md` 後半 | 自律開発Level、main merge Gate、秘匿・承認 | `docs/CODEX_AUTONOMY_RULES.md`を既存の正本として維持。Rootで短い安全原則とリンクだけ保持 |
| `frontend/AGENTS.md` | Atomic Design、MUI styled、sx/any/React.FC禁止、API、Mock | 現行のFrontend規約として拡充 |
| Backend/TF | 規約未設置 | 現行コード、lockfile、既存運用を基に新規作成 |
| `docs/CODEX_AUTONOMY_RULES.md` | ルートClosure節への直接参照 | 既存承認テンプレートとRunbookへのリンクに差替（パッチ） |

元のClosure詳細と承認テンプレートを手動比較し、4 resource更新、指定Alarmのみ削除、その他無変更、最新Artifact保持、State/lock検証、partial failure停止、閉鎖読戻し等がテンプレートに存在することを確認。承認条件の変更はしていない。

## 3. バージョンの照合

- Frontend `package.json` / `package-lock.json`：Next 16.3.4、React 19.2.8、MUI 9.4.x範囲、TanStack Query v5、Zod v4、React Hook Form v7。
- Backend `.python-version`/`pyproject.toml`/`uv.lock`：Python 3.14系、Pydantic 2系、boto3 1.43.93を確認。
- `terraform/bootstrap/main.tf` と `terraform/environments/{dev,test}/main.tf`：Terraform =1.14.9、AWS Provider ~>6.0。
- 既存の `.terraform.lock.hcl`：bootstrap/testはAWS Provider 6.64.0、devは6.65.0。**既存差異を解消しようとしていない**。
- mainのBackendにはOpenAI/Fake Provider。Bedrock・STAR統合はDraft PRの変更であり、採用方針とmain配備を同一視しない。

## 4. 公式資料（存在/内容の一部を公式サイトで確認）

- Codex AGENTS.md : https://developers.openai.com/codex/guides/agents-md
- Next.js Static Export : https://nextjs.org/docs/app/guides/static-exports
- MUI : https://mui.com/material-ui/customization/how-to-customize/
- TanStack Query retries : https://tanstack.com/query/latest/docs/framework/react/guides/query-retries
- Python 3.14 : https://docs.python.org/3.14/
- uv : https://docs.astral.sh/uv/guides/projects/
- Terraform v1.14 S3 Backend : https://developer.hashicorp.com/terraform/language/v1.14.x/backend/s3
- AWS GitHub OIDC : https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- AWS Bedrock inference profile : https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html
- OpenAI Structured Outputs : https://developers.openai.com/api/docs/guides/structured-outputs

React Hook Formのサイトへのアクセスは検証環境のページ取得エラーで未確認（リンク先の内容の検証なし）。すべての外部リンクに対する網羅的なHTTP検証は未実施。これら公式資料の確認は、現行依存にアップグレードが必要だという意味ではない。

## 5. 自己・独立観点のレビュー

- 問題1：ルートClosure節を消すと自律ルール参照が破損。対策：`docs/CODEX_AUTONOMY_RULES.patch`の参照差替。
- 問題2：Backend/terraform規約がなくCodexが個別の安全慣習を取りこぼす。対策：新規規約作成。
- 問題3：`.github/workflows/`はterraform領域外。対策：ルートとTerraform規約の双方から、Workflow変更時の明示読込みを指示。
- 問題4：mainには採用予定Bedrock実装が未merge。対策：AI方針と実装/配備済みを明記して区別。
- 問題5：既存FrontendのJSDoc必須を過度に緩和しないよう、ファイル冒頭のJSDoc方針へ修正。
- 問題6：Provider lockfile版がroot moduleごとに異なる。対策：差異とlockfile優先をTerraform規約へ反映。

## 6. ローカル静的検証

- 構造：ルートは3セクション、26行。Frontend 71行、Backend 82行、Terraform 62行。PASS。
- Markdownリンク：内部相対リンク14件すべてoverlay内かGitHubで存在確認済みの既存ファイルを参照。PASS。
- Closure参照修正：模擬リポジトリで`git apply --check`と適用のテストを実施。PASS。
- 基本的な空白：末尾空白なし。PASS。
- 読み込みスコープ：ルート・frontend・backend・terraformの経路を**規約ファイル配置と公式仕様に基づき机上確認**。Codex CLIを実起動した動作検証は未実施（このコンテナにCodex CLIなし）。
- 例題判定：Frontend/Backend/Infrastructure/複合修正・AWS操作・direct main push・実AI有料推論の分類を規約文面でレビュー。動的実行検証は未実施。
- アプリのUnit/E2E・GitHub CI・`terraform validate`：この文書パッケージでは未実施。実worktreeに適用後のGit diff/CI確認が残る。

## 7. Git/承認と未確認の残課題

- このパッケージは**オフライン成果物**。既存Gitブランチ・commit・PR・CI・merge変更はゼロ。
- 正式Apply・Bootstrap/Stage2承認、対象Hash・State・Plan・証跡を**一切使用/更新していない**。
- 適用前にmain/branch/head更新、private承認情報、未commit変更・複数worktreeの状況を本人PCで再監査する必要がある。
- 既存Bootstrap実行で参照するmain/HEAD/出典SHAの不整合を起こす可能性があるので、GitHub mergeは既存承認境界の判断が済むまで保留する。
