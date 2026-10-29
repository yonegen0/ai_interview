# GitHub capability診断とGate B再検証

2026-10-27 JST。診断の変更だけであり、GitHub-only dispatch、readiness書込み、
OIDC/AWS/State観測、Plan003、Apply、配備、実AIの承認ではない。

## 診断契約

`backend/skills/p4/github_control.py` のCLIは成功時に既存の固定marker
`GitHubEnvironmentCapabilityPassed` を1行出し、終了コード0を返す。
失敗時には次の固定キーのJSONを1行出し、必ず終了コード1を返す。
以下は架空の診断例であり、実Runの観測結果ではない。

```json
{"schema_version":1,"failure_phase":"dev-plan-variables","reason_code":"GitHubEnvironmentHttpRejected","http_status":403,"capability_result":"FAIL"}
```

- `failure_phase`: `token-preflight`、`repository-scope`、`dev-plan-variables`、
  `dev-apply-variables`、`readiness`、`unknown` のみ。
- `reason_code`: `github_control.ENVIRONMENT_REASONS` の固定allowlistまたは `UNKNOWN`。
  例外本文からreasonを取り出さない。
- `http_status`: HTTPErrorで観測した、boolを除く100〜599の整数、またはnull。
  通信失敗、JSON/件数検証失敗、readiness不一致では未観測のstatusを推定しない。
- `capability_result`: 失敗JSONでは `FAIL` のみ。

Repository APIとEnvironment variables APIは別の診断分類を使う。
HTTP401はAuthenticationFailed、404はNotFound、429はRateLimited、
3xxはRedirectRejected、5xxはServiceUnavailable、その他はHttpRejectedとなる。
接頭辞はRepository APIが `GitHubRepository`、variables APIが `GitHubEnvironment`。
403は単独ではHttpRejectedとし、権限不足を確定しない。
403で `X-RateLimit-Remaining: 0` または正の有界な数値 `Retry-After` を観測した場合だけ
RateLimitedに分類する。ヘッダ値・本文は出力しない。retryを追加しない。

通信のURLError/OSError（timeout/TLS/socketを含む）はTransportFailed、
JSON/重複キー/サイズ超過はResponseInvalid、それ以外はUNKNOWN。
既知の処理段階で未知例外が発生しても段階は保持する。
古い `GitHubEnvironmentVariablesReadDenied` は既存allowlistの互換用に残すが、
新しいHTTP403分類では生成しない。

CLIの予期しない例外にも固定JSONだけを使い、traceback・例外本文・URL・識別子・
token・PEM・認証ヘッダ・variables生値・API本文を表示しない。
出力先が壊れた場合も非ゼロ終了を維持する。
標準Plan/Applyの既存 `P4_STANDARD_FAILURE` JSON形状は変更しない。
DeploymentError互換の例外と共有reason allowlistを通して安全な理由を保持する。

## 不変条件とオフライン回帰

認証tokenの選択、期限、対象URL、Repository1件/ID/名前、pagination上限、
readinessの期待値、APIの順序・最大数、timeout、redirect拒否、retryなしを維持する。
通常成功はApp tokenによるGET3回、最大はRepository1回＋両Environment各10ページで21回。
GH_TOKENは従来のoperator/job照会専用で、App tokenのfallbackには使わない。
Git/Terraform子プロセスへApp tokenを継承しない。AWS資格取得前の拒否を維持する。

`test_github_readiness.py` はsynthetic HTTPだけを使う。Repository/両Environmentの
HTTP・通信・JSON・未知例外、token不正/期限、scope、件数、ページ不整合、
readiness不一致、秘密センチネル、CLI終了コード、標準Plan/ApplyのAWS到達前拒否、
子プロセスtoken除去を検証する。実App/IAM成功の証明ではない。

## 原因仮説（既存Run 40506644089 / Attempt 1）

| 原因候補・観測 | 分類 | 根拠・限界 |
| --- | --- | --- |
| CLIがreasonを捨てる | CONFIRMED | 固定mainソースと実Runの固定拒否marker |
| Repository APIもvariables扱い | CONFIRMED | `request_json(..., True)`。403等の誤分類が可能 |
| 通信/JSON/未知例外の混同 | CONFIRMED | variablesの包括exceptでResponseInvalidへ変換 |
| App token発行・revoke step | CONFIRMED | 両step成功、revoke marker。API成功は含まない |
| 鍵/Client ID不良でmint step自体が失敗 | RULED_OUT | 当該Runのmint stepは成功 |
| 時刻書込みの改行エスケープ不良 | RULED_OUT | 固定Workflowの書込みは通常の改行1文字 |
| WorkflowにApp token受渡し記述がない | RULED_OUT | step outputsからP4_ENV_READ_TOKENへの明示bindingあり |
| 実token形式・期限・認証/実行時刻の生値 | UNKNOWN | 生値を読まず、旧CLIに診断がない |
| installation repositories APIの拒否/ID/name/count | UNKNOWN | 到達・status未観測 |
| dev-plan/dev-apply variables API | UNKNOWN | 各到達・status・schema・pagination未観測 |
| 401/403/404/429/5xx、権限/primary・secondary rate limit | UNKNOWN | statusを旧ログから確定不能 |
| redirect/timeout/TLS/DNS/socket、JSON構造 | UNKNOWN | 旧ログから区別不能 |
| readiness欠落/不一致/伝播、実行環境変数 | UNKNOWN | 復帰後のoperator readbackは過去Run中のApp応答を証明しない |
| installationの実scope/権限 | UNKNOWN | owner確認資料はあるがApp tokenの真正API成功は未証明 |

上段のCONFIRMEDは診断欠陥であり、過去Runの直接原因が確定した意味ではない。
特定のAPI障害をPROBABLEに格上げする証拠はない。
新たに承認された単回実証では、失敗した場合も最初に拒否した段階・有限reason・
観測できたHTTP statusが分かる。403の直接的な権限原因や過去Runの原因まで
自動的に確定するわけではない。

## 新規単回承認の準備条件

診断PRの通常mergeと真正CI成功後に最新source/mainとWorkflow commit/blobを固定し、
別の承認資料へ記録する。旧承認は消費済みで再利用しない。
対象は `p4-standard-qualify.yml`、mode=github-only、operation=plan、Attempt1を1回だけ。
dev-planの2flagをtrueにし、成功/失敗/途中例外にかかわらずfalseへ戻す。
dev-applyを書き換えない。readiness書込み最大4回。事前/active/終了時に両Environmentを読戻す。
API読取り・監視時間の上限とcleanup用の予約枠も新資料で固定する。
source移動、競合運用Run、全4flag=falseでない状態、APIエラー、期限/予算超過、
失敗/不明ではdispatch/rerunを追加せず停止する。cleanup不明なら公開/Plan003へ進まない。

GitHub-only真正PASSと全4flag=false復帰後にのみPlan003正式承認パッケージを完成する。
State13等の既存資料は歴史証拠のまま扱い、fresh AWS/State/Stage/lock/入口閉鎖観測と
新規72時間・単回承認がそろうまではPlan003を実行可能にしない。

公式根拠:
[Environment variables API](https://docs.github.com/en/rest/actions/variables#list-environment-variables)、
[installation repositories API](https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation)、
[REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit)。


## 単回実証40522761747とopaque token形式互換性

2026-10-27、固定source `ec5a39030afe43759b9262282658d2d1ba880bef` の
[GitHub-only Run40522761747 / Attempt1](https://github.com/yonegen0/ai_interview/actions/runs/40522761747)
はFAIL。安全な診断は `token-preflight / GitHubEnvironmentAuthenticationFailed / null`。
Repository/両Environment APIへ到達する前のローカル拒否であり、HTTP401/403/404/429/5xx、
transport、schema、実scope、App経由readinessの成否は未観測。mint/post成功、revoke markerと
OIDC job SKIPPEDを確認し、dev-planへの計4PATCH後、両Environment全4flag=falseを読戻しVERIFIED。
秘密値・生ログは保存せず、時刻は数値かつRun時間内というbooleanだけを投影した。

CONFIRMED: 既存 `[A-Za-z0-9_]+` は公式stateless形式に含まれるドット・ハイフンを拒否する。
合成tokenだけで同じphase/reason/statusを再現した。
GitHubは2026-10-02に `ghs_APPID_JWT` への移行完了を公表し、tokenをopaqueとして扱うよう案内している。
この互換性欠陥を最小修正し、許容文字を `[A-Za-z0-9_.-]+` とする。
JWTのdecode/署名判定、固定長、token保存、代替資格、opt-out header、権限追加は導入しない。
期限・repository ID/name/count・readiness・URL・要求数・redirect拒否・retry0を維持する。
空文字、空白、改行、制御文字、非ASCII、その他のheader不適合文字は引き続き拒否する。

PROBABLE: 今回のtoken-preflight拒否は新形式と旧正規表現の不整合。
実tokenのbytesを調べていないため、形式・内容や修正後の真正API成功を実測済みとはしない。
旧Run40506644089やPlan002の過去の直接原因はUNKNOWNを維持する。
オフライン試験と通常CIは実App/AWS/IAM成功の証明ではない。

当該単回承認は消費済み。修正sourceへ転用せず、新しいsource/main、Workflow blob、CI、
readiness、回数・時間・cleanupを固定した別の明示承認後にだけ次のGitHub-only Attempt1へ進む。
Plan003正式承認資料はINCOMPLETE、Plan003実行NOT_AUTHORIZED、Gate B/公開NOT_READY。

公式根拠:
[新形式の展開完了](https://github.blog/changelog/2026-10-02-stateless-github-app-installation-tokens-rolled-out/)、
[opaque形式・許容文字の公式案内](https://github.blog/changelog/2026-05-15-github-app-installation-tokens-per-request-override-header/)。
