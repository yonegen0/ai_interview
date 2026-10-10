# ai_interview Codex自律実行ルール Ver.2.0

2026-10-11のユーザー指示に基づく。最新の個別指示とシステム権限が優先する。
調査→判断→実装→重点検証→問題修正→再検証→許可範囲内の反映→報告を完了する。
作業量でなく可逆性、影響範囲、損失・セキュリティ・課金リスク、確信度、既存承認範囲で判断する。

## 自律範囲

| 区分 | 作業 | 実行条件 |
| --- | --- | --- |
| Level 1 | コード/履歴/証跡/公式資料調査、最小修正・軽微なリファクタ、単体/結合検証、lint/型/ビルド、Mock/FakeProvider、Terraform fmt/validate/offline mock、隔離worktree、資料/hash検証 | 依頼範囲内で個別確認不要。成功検証はHEAD・依存・入力・条件が一致すれば再利用 |
| Level 2 | 作業branchの通常commit/push、Draft PR作成/更新/解除、CI修正、低リスクmain merge、事後CI確認 | 権限・安全Gate成立。force push/direct main push/保護bypass/無断branch削除は禁止 |
| Level 3 | CI/テスト/型/import/依存/限定仕様の不整合、明確なP1、軽微なTerraform監査不具合、再現可能な競合/例外 | 根本原因→再現テスト→最小修正→回帰検証→影響評価→元作業再開。約3つの異なる修正案で未解決、または影響拡大なら停止 |
| Level 4 | 実Terraform Apply、State変更/削除/移行、重要IAM変更、AWS配備/Enablement、有料OpenAI、実利用者データの破壊、重大セキュリティ変更、保護解除/迂回、不可逆操作、課金上限を保証できない操作、原因不明重大障害、証跡/State/Plan不整合、P0/困難なP1 | 停止し、具体的な対象・影響・復旧方法・最小の必要承認を提示 |

P1は発見直後に放置せず、安全なローカル修正が可能なら解消する。高リスク境界を越える修正は承認まで実行しない。

## main mergeの必須Gate

1. P0/P1未解決0件。
2. 全必須CI成功。
3. 最新HEAD/base/mainが監査対象と一致。
4. 競合・未解決レビューなし。
5. GitHub保護・rulesetを遵守。権限不足を保護なしとみなさない。
6. 未承認のAWS配備・外部副作用を起動しない。
7. 認証・IAM・State・決済・機密情報等の高リスク変更がない。
8. 既存機能の互換性を保持。

一つでも未成立ならmergeを停止する。安全な修正・確認は自律的に完了してから判断する。

## AWS・一括承認

完全サーバーレス・無料枠優先・固定費最小化を維持する。read-onlyでも実AWS接続/State読取りは、
事前承認されたAccount/Region/資源/目的に限定する。read-onlyを理由に承認を省略しない。
承認パッケージは事前Gate、State/Artifact/Plan/hash、実行対象・回数・費用上限、本処理、事後検証、
証跡保存、必要なClosureと閉鎖確認を含める。承認後は範囲内の全工程を追加の細かな確認なく完了する。
費用見積りやdescriptorの上限は、請求を技術的に強制停止する保証とは区別して明示する。

P4一時Enablementの正常・異常経路はAGENTS.mdの条件付き自動Closure、
[承認テンプレート](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)、[runbook](P4_TERRAFORM_RUNBOOK.md)に従う。
Enablement成功かつState/AWS実体が正常なら、Smoke/性能のPASS/FAIL・inbox未確認によらず閉鎖まで完了する。
applyのpartial failure、State不整合、lock、Closure差分の逸脱時は再applyや手動修復でClosureを強行せず、read-only診断で停止する。
Closure失敗・結果不明を閉鎖成功とみなさず、新規作業を停止する。性能Gateを後付け変更しない。

## 保全と現在工程

Coaching V2（30点/深掘り）、V1互換、STAR Ver.1.4、本人分離・冪等性・Recovery、既存Session/Attempt/Evaluationを維持する。
既存Git履歴/worktree、Plan/State/journal、private ledger/監査証跡を破壊・上書きしない。
過去の資料の「当時の個別承認待ち」は履歴として保存し、現在の低リスク作業には本ルールを適用する。
新指示は高リスク承認済みの意味ではない。sandboxや承認設定を変更しない。

現在の優先工程はBootstrap正式監査復旧の準備。clean main共通Git dirの実行元、fresh descriptor/hash、
オフライン事前監査、1回限りのread-only復旧承認パッケージまで自律的に準備する。
AWS接続・State読取り・正式復旧は具体的な明示承認後のみ。
Bootstrap Apply、STAR配備、実OpenAIは別承認。
正式復旧失敗/timeout/不明/途中完了時は証跡を保持して停止し、再実行・別run回避・ledger削除・修復をしない。

## 報告

中間報告は重要進捗・重大リスク・判断不能事項に限定する。
最終報告は完了作業、発見/修正、検証、Git/CI、AWS/費用、残リスク、正式status、次工程を簡潔に示す。
停止時は理由、解決済み範囲、危険/未確認事項、最小の承認/対応、承認後の自律実行範囲を明記する。
