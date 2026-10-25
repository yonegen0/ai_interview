# AGENTS.md最適化 — オフライン作成パッケージ（2026-10-19）

対象 `yonegen0/ai_interview`、GitHub main観測SHA: `ca4d7976e779473b6d0650f9f69484705bdb5798`。
このパッケージは**2026-10-19の作成時点でリポジトリへ未反映でした**。同日の作成ではAWS、Terraform、GitHubへの書き込み、有料AI推論を行っていません。

## 含まれる変更

- `AGENTS.md`：ルート48行→26行、恒久ルールを3見出しに限定。
- `frontend/AGENTS.md`：既存32行→71行、Next.js/React/安全なAPI・認証・検証/公式資料を拡充。
- `backend/AGENTS.md`：新規82行。
- `terraform/AGENTS.md`：新規62行。
- `docs/CODEX_AUTONOMY_RULES.patch`：既存のClosure参照を承認テンプレートとRunbookへ差し替える1箇所だけのパッチ。

## 安全に適用する手順（人またはCodexがローカルで実施）

1. 最新main、`git status --short`、`git worktree list`、Bootstrap進行中の承認・作業ツリーを事前確認する。
2. `git merge-base`等で差分を比較し、既存の未コミット変更を上書きしない別作業branch/worktreeを使う。
3. 4ファイルを同じ相対pathへコピーする。`docs/CODEX_AUTONOMY_RULES.patch`を `git apply --check` → `git apply` する。
4. `git diff --check`、相対リンク検証、変更ファイルの監査を行う。必要なDoc/CI検証を実施する。
5. `main`への直接push・force pushはせず、既存の安全Gate/承認範囲に従ってPR作成・mergeの可否を判断する。

**注意**：既存root AGENTS.mdにあるP4一時Enablement/Closure詳細は、既存の `docs/P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md` にすでに記載されていることを確認。内容を破壊せず、その正本へ参照を張り替える。テンプレートを同意なく書き換えない。

## 検証の境界

このパッケージはGitHubのmainにある文書/設定を読み取り、独立したコンテナで文書を生成したもの。ユーザーPCの未コミット変更、lock、承認Ledger、worktree、実際のCodexのAGENTS読込みは確認していない。パッチの実repoでの適用、`git diff --check`、CIは未実施。実AWS・実AI検証もしていない。
