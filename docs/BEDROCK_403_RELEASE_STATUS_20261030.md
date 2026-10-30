# Bedrock 403の原因分類と公開前の検証状況

2026-10-30 JST。調査基準mainは `85d51761864b3e01aa881912bc54fb3eb0650624`。
本記録は実行承認ではない。新規AWS接続・Terraform実行・モデル送信・公開は行っていない。
アプリ、IAM、Terraform、依存、モデルIDを変更する根拠は見つかっていない。

## 403の判定

**分類D：アカウント単位のモデル利用制限に一致する応答。内部の制限理由・解除条件はAWS確認待ち。**

保存された実行では、SSO主体による直接Converseの1送信がHTTP 403
`AccessDeniedException` となった。`is not available for this account` と
AWS Salesへの案内を含む文言は、[AWS公式の障害説明](https://repost.aws/knowledge-center/bedrock-invokemodel-api-error)
のアカウント制限の説明と一致する。同資料は、この制限はコンソールに表示されず、
IAMやmodel access設定の変更では解消できない場合があること、Supportへの連絡を案内している。
したがってIAM拡大・モデル切替・推論の再送で解消を試みない。

| 分類 | 保存証跡との照合 |
| --- | --- |
| A：IAM/SCP | 今回の応答は公式のアカウント制限の説明に一致する。SSO/Workerの実効IAM・SCP全許可を証明したわけではない |
| B：modelId/Region/profile | `jp.anthropic.claude-haiku-5-5`、送信元Tokyo、ACTIVE profileの宛先Tokyo/Osakaが公式仕様と一致 |
| C：契約/FTU/支払 | 既存agreementの作成・独立確認済み。保存された管理APIはagreement/entitlement/region=AVAILABLE、authorization=AUTHORIZED。FTUのGetはHTTP200・非空。現在の支払状態・FTUの追加条件は未確認 |
| D：アカウント制限 | 応答文言により強く支持される。具体的な制限理由と解除可否はAWS側で確定する |
| E/F：その他/不足証拠 | 現在のquota、元呼出の正確なassumed-role ARN、実wire endpointは未取得・未保存。不存在とみなさない |

[モデルの公式資料](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html)
はJP profileの送信元・宛先をTokyo/Osakaと定義する。保存されたSDK構築コードは
`bedrock-runtime`、`ap-northeast-1`を指定する。標準endpointは
`https://bedrock-runtime.ap-northeast-1.amazonaws.com` と導出できるが、元送信のwire URLの保存証拠とは区別する。

[Geographic cross-Region IAM仕様](https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html)
では、profile、送信元foundation model、各宛先foundation modelへの許可と、宛先Regionを拒否しないSCPが必要。
管理APIのAVAILABLE/AUTHORIZEDだけをConverseやWorkerの実効権限の保証にしない。

## 実施したオフライン確認

- 調査基準mainのBackend/Frontend/P4 offline workflowは成功。Backend verify、Frontend verify、
  terraform、package_changesが成功し、変更のないpackage jobは設計どおりskip。
- Backend/契約/Terraformは、実AI検証時の `de4cab8d7809d0bba81482e1023af21c07eb2600` から無変更。
  同一のBackend実装・依存・fixtureに対する重点テスト272件PASS。
  Bedrock boundary/Worker、STAR prose/live adapter/保存、Coaching V2/binding、Hosting rewriteを含む。
- MockでSTARの出典・数値・否定・条件の保持、入力命令の混入、不正schema、Timeout、
  二重送信防止、Coachingの契約・本人分離を検証。実モデルの自然さ・採点品質・速度の評価ではない。
- 既存production ZIPを現mainの安全検査で再検証。7ルート、Mock資産なし、
  API `/dev`とCognito public configが保存済みState 24に一致。
  ZIP作成時からのFrontend差分は安全検査scriptとそのテストだけで、製品ソースは無変更。
  既存ZIPを再利用しており、新規build/upload/公開はしていない。
- Support向けの時刻・Request ID・完全なエラー・modelId・Region・管理APIの観測と
  未確認事項を、本人限定のローカル下書きに整理済み。送信はしていない。
  Account識別子、資格情報、State、Plan、回答本文、private証跡を本リポジトリへ追加しない。

## 性能・実AI・閉鎖の判定

| 項目 | 判定 |
| --- | --- |
| 直接Converse | 既存1送信FAIL/403、retry 0。今回の追加送信0 |
| Worker実AI | 未実施。SSO直接Converseと区別する |
| STAR/Coaching実AI品質 | 未評価。Mock成功で代替しない |
| Fake30人 | [既存正式測定](P4_DEV_PERFORMANCE_ANALYSIS_20261006.md)のScenario C、63 API要求のnearest-rank p95=2003.466ms、FAILを維持。30評価の完了確認9.283秒 |
| 性能Gate | 既存規則のAPI cold込みp95≤2000ms、30評価≤30秒を保持。新規測定なし。閾値・母集団・percentileの変更なし |
| 実AI30件 | 未実施・未承認。最初の疎通成功前に開始しない |
| AWS閉鎖 | 保存された独立プロセス監査はPASS。dev serial24/77資源、Bootstrap serial9。4入口閉鎖、readiness全false、lockなし、Alarm0、Lambda/alias/Artifact/IAM保持 |
| 現在のAWS State | 新規読取り未承認のため再取得なし。保存済み閉鎖証跡を現在の実AWS再監査とは呼ばない |
| GitHub readiness | 本調査時に両Environmentの全4項目falseを再読取り確認 |
| Cognito/API E2E | ユーザー指定により保留継続 |
| 費用 | 元403にusageなし。実請求額未取得。ゼロ請求とは断定しない。今回のAWS操作・モデル送信は0 |

## 公開までの残条件

公開判定は **NOT_READY**。

1. 元Request IDを用いてAWS Supportへ問い合わせ、アカウント制限の解除条件を確認する。
   送信と新規read-only調査は必要なscope・上限をまとめて承認する。
   契約/FTU書込み、Support有料プラン変更は承認に含めない限り実行しない。
2. 制限解消後、新しい明示承認でAccount/Region/State/lock/閉鎖状態・適用JP価格を再確認する。
   送信件数・モデル・費用・Enablement/Closure回数を固定し、直接Converse成功後にWorkerへ進む。
   既存承認の直接送信1回とApply/Closureは消費済みで、追加送信枠は0。旧saved Planを再利用しない。
3. STAR/Coachingの実品質と必要な実AI性能を、承認枠内で評価し、必ずClosureと独立読戻しを完了する。
4. 正式Fake30人測定には、実AWSの一時Fake切替と復元の環境変数/version/alias/IAM差分、
   cold条件、試験主体の扱いを確定する。4フラグだけのEnablement承認では代用できない。
   30要求を30本人の検証と呼ばない。現行Bedrock WorkerへFake試験を送らない。
5. HTTPS Originを確定し、CORS・Hostingの具体差分を準備する。現状のCORSは保存証跡上localhostのみ。
   DNS/Hosting公開・恒久入口開放は別の承認境界。Cognito/API E2Eは保留解除まで実行しない。

上記の実AWS条件が揃うまでは、修正根拠のないコード変更や再Enablementを行わない。
