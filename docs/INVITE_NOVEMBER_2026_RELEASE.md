# 2026年11月 招待公開の最小構成

対象は既存ADMIN/USER、将来合計12名程度。新規ユーザーの作成権限、JWT検証、本人別データ分離は変更しない。
公開準備の実装であり、この文書自体は配備・実受入の成功証跡ではない。PR #43はHOLDを維持する。

## 監視

invite環境だけを`minimal`に切り替え、既存dev/testの監視契約は維持する。

| Alarm | 検知対象 | メトリクス |
|---|---|---|
| api-5xx | API主要障害 | AWS標準1系列 |
| worker-Errors | Worker例外・タイムアウト | AWS標準1系列 |
| dlq | Worker DLQ、Streams失敗キュー | AWS標準2系列のSUM |
| CriticalFailure | 保存整合性、DB、処理失敗、結果不明、滞留 | カスタム1系列 |
| RecoveryHeartbeat | 回復処理の停止・不完了 | カスタム1系列 |

**5 Alarm / 課金対象6メトリクス / カスタム2系列**。全て標準解像度。
CriticalFailureは全コンポーネントをProject/Environment次元で集約し、ユーザー別次元を作らない。
認証回数・成功回数・処理時間はカスタムメトリクスにしない。既存の内容を含まない障害・利用量ログは維持し、保存は3日。
Recoveryは既存の毎分実行を維持する。Budgetsは通知のみを使い、課金を即時停止する仕組みとは扱わない。

## Claude利用制限

- 20回/人、600回/全体は利用目安。サーバーの緊急上限を**100回/人/月、2,000回/全体/月**へ変更。
- 通常・Coachingは従来どおり同じ原子的Providerカウンタを共有。STARは既存の独立カウンタで同じ100/2,000を適用。
- 従って合算上限は200回/人、4,000回/全体。カウンタ統合やDB移行は行わない。
- 従来の月区切りを維持（ProviderはUTC、STARはJST）。過去の消費・予約をリセットしない。
- 1回の入力サイズ、通常/Coaching出力4,096 token、STAR出力2,048 token、SQS同時実行2、リトライ・冪等性・回復処理を維持。
- Bedrock/OpenAIの設定上限は従来20/600のまま。自動フォールバックは行わない。
- ClaudeはAWS費用と別会計。受入用のエージェント有料実行9回/USD0.05という既承認上限は変更しない。

[Anthropic公式料金](https://platform.claude.com/docs/en/about-claude/pricing)のHaiku 5.5、入力USD0.10/MTok、出力USD0.50/MTokを使用。
入力を通常20,000 token、STAR24,000 tokenと置き、出力上限まで使う試算では通常1回USD0.004048、STAR1回USD0.003424。
この入力条件で緊急上限を双方使い切る試算額はUSD14.944。これは通常利用予算・請求hard capではない。
12名がそれぞれ通常20回＋STAR20回なら同じ条件でUSD1.79328。実際は利用量ログで集計する。

## 期限と閉鎖

期限は**2026-12-01 00:00 JST（2026-11-30 15:00 UTC）**。
CloudFront viewer-requestとAPIのサーバー側時刻判定で、キャッシュ済み配信・既存セッションを含め期限以降の新規アクセスを拒否する。
同時刻の一回限りSchedulerが専用Lambdaを呼び、API、2つのEvent Source Mapping、Recovery、CloudFrontの5入口を停止する。
CloudFront反映後に別のGETで全入口の状態を読戻し、全て閉鎖済みの場合だけ5 Alarmを削除し、削除も読戻してSNSへ通知する。
Schedulerは秒単位の正確な起動を保証せず、CloudFront停止には反映待ちがあるため、アクセス期限はSchedulerに依存させない。
既存の処理中要求が期限後に完了することはある。新規受付拒否と物理停止完了は区別する。

追加権限は専用の`close-runtime`/`close-trigger`と専用Boundaryに限定する。
対象API、2つのMapping、Recovery Schedule、Distribution、5 Alarm、通知先、失敗キュー、専用ログだけを指定する。
既存の業務ロールに権限を追加せず、DynamoDB・Secretsへの権限を付けない。
失敗通知先キューだけに専用2ロールのSendMessageを許可する。閉鎖実装は入力イベントから対象を変更できない。
Update API/Distribution自体はAWS IAM上で閉鎖方向だけに制限できないため、固定コードと対象ARN、事前時刻検査で閉鎖方向を保証する。
同じ関数を自分で再起動する権限は付けない。Lambda非同期再試行は最大2回、SDKは1実行48要求以下。
自動閉鎖はTerraform管理属性を変更するため、次の公開前には閉鎖済み実体をrefreshして新しい監査済みPlanへ反映する。古いPlanを再利用しない。

## AWS費用の計算条件

期間は11月3日22:20から12月1日00:00まで、約649.67時間。遅れた公開開始分は減る。
12名、通常/STAR合計480〜2,400回、API最大100,000要求、OTP最大360通、ログ1GB未満、DynamoDB本体/PITR各0.1GB未満を通常利用の試算範囲とする。
無料枠の現在使用量は別の非公開証跡で取得する。将来の他用途との競合や計上遅延は残る。

| サービス | 無料枠適用と東京の試算 | 期間追加額 USD |
|---|---|---:|
| CloudWatch | 10 Alarmメトリクス、10カスタム、ログ5GBの共通枠内なら無料。変更後は6/2。過去の時間比例使用量も加算 | 0 |
| Lambda | 100万要求/40万GB秒の共通枠。Recovery約38,980回と通常利用・閉鎖を含む | 0 |
| SQS / Scheduler / SNS | 月100万SQS要求、1,400万Scheduler呼出、SNS通知枠内を想定 | 0 |
| DynamoDB | **PAY_PER_REQUESTを維持**。25GB保存無料でも読書きは有料。USD0.715/M WRU、0.1425/M RRU。Recoveryの4カーソル書込みも含む | 0.28〜0.65 |
| DynamoDB PITR | 無料枠と別。USD0.228/GB月、0.1GB未満 | 0〜0.023 |
| Cognito Essentials | 直接認証12MAU、組織/アカウント共通10,000MAU枠内 | 0 |
| SES | 旧3,000通/12か月の資格・残期間を確認できないので**控除しない**。最大USD0.16/1,000通で360通＋データ | 0〜0.060 |
| CloudFront | アカウント共通1TB/1,000万要求のpay-as-you-go枠内。Function要求は保守的に有料計上 | 0〜0.010 |
| API Gateway HTTP API | 期限付き無料枠を控除せずUSD1.29/M要求、10万要求以下 | 0〜0.129 |
| Secrets Manager | 専用Secret 1個USD0.40/月を時間比例＋取得要求 | 0.361〜0.381 |
| S3 | 静的ファイル・Artifact・State・要求。期限付き無料枠は控除しない | 0〜0.050 |
| Budgets | 通知・監視のみ。Actionsや有料レポートは追加しない | 0 |

**合計試算 USD0.65〜1.41、運用余裕込み申請上限USD2.00**。消費済み無料枠・他用途増加・異常トラフィック・税はこの推計を超え得る。
SecretsとオンデマンドDynamoDBが残るため、構成を維持したまま完全なUSD0にはならない。
当月のPAIDプラン、クレジット残高0、Always Freeの使用量は実APIで確認済み。期限付き枠は資格・終了日が未確認なら計算に入れない。
USD6.00への増額は使わず、この再計算後の差額について別途承認を受ける。

料金正本: [AWS東京リージョンのPrice List](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/ap-northeast-1/index.json)、
[CloudWatch](https://aws.amazon.com/cloudwatch/pricing/)、[Cognito](https://aws.amazon.com/cognito/pricing/)、
[SES](https://aws.amazon.com/ses/pricing/)、[CloudFront](https://aws.amazon.com/cloudfront/faqs/)、
[Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/)、[Budgets](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)。
公開前には通常利用の範囲と、請求通知に遅延があることを運用者が確認する。
