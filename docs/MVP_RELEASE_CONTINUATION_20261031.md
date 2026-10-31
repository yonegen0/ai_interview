# 公開準備の継続確認（2026-10-31 JST）

## 状態と保全

**公開はBLOCKED。** Issue #92の必須dev audit、既存AWS性能FAIL、実認証・実効IAM・実AI・公開経路の未検証を維持する。main mergeはChatGPT担当、Codexは実施しない。#104は検証専用・merge禁止、#43/#50はHOLDのまま。

作業開始時のGitHub mainは`7e7fa78e5ff34a998f1d1530c1fafe8ce82cf2b8`。元workspaceの未コミット変更には触れず、このmainから`codex/release-continuation-20261031`を作成した。アプリ、依存、lockfile、Terraform、CI設定の変更はない。

Ruleset `24886774`はactive、bypass actorなし、strict base・レビューthread解決を要求し、必須チェックは`Backend verify` / `Frontend verify` / `terraform` / `package_changes` / `package`の5件。対象12件と#104は全件Draft・未merge。FrontendはFAIL、Backend/オフラインTerraformは成功。`package`の条件付きSKIPは実パッケージ検証PASSと同一視しない。

| PR | 確認したHEAD |
| --- | --- |
| #91 | `86151025e98888a0633212ee39df672101cf61b9` |
| #93 | `55b59690fd3340453dff99748f70d7e6e884648d` |
| #94 | `8df9bf4517ab78b5013dabbcb0b933217620318e` |
| #95 | `6baa4e5ecd3d82097a86014df5faccd1b6ae3cd4` |
| #96 | `ef82e76f37551757b07de955e451a5fc25526692` |
| #97 | `0a61f37ea48eb9a59c3e2d7af3bd0d23236df3f2` |
| #98 | `078132cd3623155acead5a9a50dea3dffc443081` |
| #99 | `acb32819b2931b58ef8bc4dee910f83945f7479b` |
| #100 | `f81aec26d2375f466319b1d97cb673d5b77ac18b` |
| #101 | `4bcf4144fede35b502126cfdc1f29a22423c8afc` |
| #102 | `e970576b6df303143e35fb7b45db5881c2aa6c28` |
| #103 | `f4023f24d76de41b6488a5d51df8749006ccc38b` |
| #104 | `f437016a0b65e24e024cf97c0aeb4005f2e98567` |

## Issue #92：BLOCKED、依存変更なし

公式npm registryのlatest metadataを再取得し、既存調査と比較した。以下の重要な版・依存範囲は変わっていない。依存更新実験・再install・同じauditの再実行はしていない。

| 公開された依存元 | latest | 公開依存範囲 |
| --- | --- | --- |
| eslint | 10.14.0 | minimatch `^10.2.6` |
| @eslint/config-array | 0.23.5 | minimatch `^10.2.4` |
| @eslint/eslintrc | 3.3.7 | minimatch `^3.1.5` |
| eslint-plugin-import | 2.32.0 | minimatch `^3.1.2`、ESLint peerは9まで |
| eslint-plugin-jsx-a11y | 6.10.2 | minimatch `^3.1.2`、ESLint peerは9まで |
| eslint-plugin-react | 7.37.5 | minimatch `^3.1.2`、ESLint peerは9.7まで |
| @typescript-eslint/typescript-estree | 8.72.1 | minimatch `^10.2.2` |
| @joshwooding/vite-plugin-react-docgen-typescript | 0.9.0 | glob `^13.0.6` |
| @storybook/react-vite | 10.6.5 | docgen plugin `^0.7.0` |

minimatch latestは11.0.3、glob latestは14.0.3だが、安全版を依存元の範囲で解決できない。[minimatch GHSA](https://github.com/advisories/GHSA-g3hv-75wg-m249)の修正版は11.0.1以上、[glob GHSA](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)は14.0.2以上。[ESLint公式10.14.0リリース](https://eslint.org/blog/2026/10/eslint-v10.14.0-released/)もminimatch 10.2.6への更新を記録している。

既存auditはdev 21 moderate / prod 0。21 findingsは2 advisoryから依存元へ波及した件数。互換性未確認のmajor override、ルール/docgen削除、lockfile手編集、閾値緩和は行わない。再開条件は**上表の全依存経路に互換性のある安全な公開版が揃うこと**。その後npm正規生成、npm ci、dev/prod audit low、全Frontend品質検証を通し、専用修正Draft PRを作成する。

一次資料の例：[ESLint registry](https://registry.npmjs.org/eslint/latest)、[TypeScript ESLint registry](https://registry.npmjs.org/@typescript-eslint%2ftypescript-estree/latest)、[docgen registry](https://registry.npmjs.org/@joshwooding%2fvite-plugin-react-docgen-typescript/latest)。他の表のmetadataも同じ公式registryから取得した。

## ローカル・CI証拠の再利用：PASS（対象範囲限定）

`git merge-tree --write-tree f437016 ef82e76`と`git rev-parse 'f437016^{tree}'`は両方とも`b8b2990b591397e7f9298f1d966edc257e511c9c`。#96の新HEADを#104へ統合してもソース全体が同一になる。修正テストのblobも両方`a0e2d350ccc23e8ab197cda9a9f459831f7c1d2d`。他11件のHEADとmainは既存検証時と同一。Terraform、依存、規約にも差分がないため、次の証拠を再利用する。個別PR/最新mainのCIが新たに成功したという意味ではない。

| 対象 | 証拠・判定 |
| --- | --- |
| Frontend機能 | [run 41173130952](https://github.com/yonegen0/ai_interview/actions/runs/41173130952)：npm ci/lint/typecheck、68ファイル・701 tests、本番Static Export/安全検査、Storybook、Mock build、37 Mock E2EはPASS |
| Frontend必須job | 同runのdev audit 21 moderateで**FAIL**。prod audit 0。個別PRではaudit後のテストがSKIPのものがある |
| Backend Linux | [run 41173130999](https://github.com/yonegen0/ai_interview/actions/runs/41173130999)：Ruff、3,665 passed / 2 skipped / 57 deselected、契約102件、Ed25519 9件、demoはPASS |
| Terraform offline | [run 41173130934](https://github.com/yonegen0/ai_interview/actions/runs/41173130934)：fmt、6root validate、service60/bootstrap15/frontend2の77 Mock、locked Linux ZIP/socket遮断importはPASS |
| Windows | [環境診断と再現手順](P4_WINDOWS_TEST_ENVIRONMENT_20261031.md)。3ファイル82件PASS。統合HEAD全体は**3,636 passed / 14 failed / 17 skipped / 57 deselected / 0 error**。40件のACL失敗・9件のOpenSSLエラーは再発せず、残る14件はPOSIX API/symlink制約。全体判定は**FAIL** |

検証版はNode 22.23.4 / Python 3.14.9 / Terraform 1.14.9。今回端末のNodeは24.22.1、npm11.19.1。異なる環境で全Frontendを再実行したとは記録しない。

認証状態/本人切替/401書込み非再送・GET refresh/キャッシュ/STAR下書き・Recovery/Coaching制限は既存Frontend証拠、Claude Mock/STAR根拠/JWT owner/冪等・Quota/SQS重複/Recovery/エラー分類/ログ/本文上限は既存Backend証拠の対象。実AWS・実AIの保証には転用しない。

## Cognito準備：公式照合PASS、実設定と停止原因はBLOCKED

[AWS属性仕様](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html)では`sub`はCognitoが割り当て、他の標準属性は既定で任意。`SchemaAttributes`の`Required`を実設定から確認する。emailをusernameとする要件と、schemaのRequired一覧は分けて照合する。

`OtherRequiredAttributesNeedReview`で停止した作成スクリプトの該当コードと、その時のSchemaAttributes応答を今回確認できていない。`sub`を利用者入力必須と誤認した可能性は仮説に留める。未知の必須属性を空値で埋める、pool schemaを変更する、ガードを削除する、ユーザー作成を再実行することはしない。

`terraform/modules/service/auth.tf`はEssentials、email username/auto verification、admin-create only、PASSWORD+EMAIL_OTP、MFA OFF、secretなしclient、USER_AUTH/REFRESH_TOKEN_AUTH、USER/ADMIN群、JWT issuer/audienceを定義する。これは期待設定であり、実AWSへの反映証拠ではない。[AdminCreateUser公式仕様](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)のSUPPRESSやpassword省略条件も作成前に確認する。今回は作成・OTP送信を行っていない。

最初に必要な承認は既存dev pool/clientの限定metadata読取りだけ。private承認資料に既存ローカル読取りスクリプトから確認したAccount/Region/pool/client名とsource SHAを固定した。最大6 API操作（STS1、DescribeUserPool1、ListUserPoolClients1ページ、DescribeUserPoolClient1、GetGroup USER/ADMIN各1）、再試行0、作成/更新/OTP/State/Secret値/有料AIは0。現時点では未承認・未実行であり、この文書は実行承認を与えない。

## 配備・品質・公開までの順序

| 工程 | 今回できた準備 | 次の成立条件 |
| --- | --- | --- |
| 認証・USER/ADMIN | schema照合、OTP→JWT→refresh/logoutと本人切替の既存手順照合 | 限定読取り後に必須属性の原因確定。別途2名の作成/群割当/OTP配送の明示承認 |
| JWT/本人分離/DDB/SQS | 既存auth_e2e/契約/重複配送/Recoveryの証拠を対応付け | 対象artifact/実alias/テストデータ/操作回数を固定した実サービス承認 |
| 直接Claude API | Mock・schema・終端分類・worker限定Secret/IAMの既存検証を再利用 | Secret名/ARN・値投入方法・実効IAM・明示Provider入力・固定model/API版をレビュー。Secret読取り/投入、IAM変更、配備、実推論は未承認 |
| STAR/Coaching品質 | 既存12品質ケース、STAR A/B/C根拠・否定/数値、Coaching1回1論点、再推論禁止を再利用 | 既存提案のSTAR最大12+通常最大6送信を上限に、対象Providerの最新公式単価/入出力/費用/時間/停止条件を別承認。自動retry0 |
| AWS性能 | 正式Gateと既存計測条件を保持 | p95 **2003.466ms FAIL**を維持。同じScenario Cで測定。30件9.283秒はFakeのみ。実AI30件/30秒は別費用承認 |
| HTTPS hosting | 既存非公開S3/OAC・CloudFront手順、production out安全検査を再利用 | exact build digest/public settings/Origin/配備先/rollback条件を固定。upload/CloudFront公開は別承認 |
| Closure | [既存テンプレート](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)と[Runbook](P4_TERRAFORM_RUNBOOK.md)を保持 | Plan/Applyの独立承認。正常enablement後は試験FAILでも承認済みClosureへ進む。partial failure/State・lock不明は再applyしない |

ユーザーの今回目標は直接Claude APIを本番標準とすること。既存リポジトリのBedrock JP Geo標準という記述、直接APIの実装・Mock検証、現在の実配備Providerを区別する。今回Provider設定/採用文書の一括変更・切替・自動fallbackは行っていない。

現在のsourceに適合する、未消費で有効なAWS実行承認は確認できていない。古い承認や過去のState/Planを流用しない。read-onlyも承認対象という[自律実行規則](CODEX_AUTONOMY_RULES.md#aws一括承認)と[Runbook](P4_TERRAFORM_RUNBOOK.md#0-実行前提)により、実環境工程だけを停止している。

ChatGPTへの引継ぎはIssue #92をOPEN維持、全必須CI成功後の個別PR統合、#96テスト修正同伴済みの確認、共有Anthropicテストと#99/#100の両ガード保持、#104 merge禁止、#43/#50 HOLD維持。統合後の新main/入力/依存差分に応じて必要な回帰だけを再実行する。

ローカル証跡は専用worktreeと同階層の`evidence/`へ新規保存した。registry metadata、全PR SHA/check snapshot、Ruleset、既存CIの実ログ、Windows比較ログと分類を含む。private State/Plan/ledger・資格情報・メール・JWT/OTPはコミットしない。AWS接続/読取り、実Plan/Apply、配備、有料推論はすべて**NOT_RUN**。
