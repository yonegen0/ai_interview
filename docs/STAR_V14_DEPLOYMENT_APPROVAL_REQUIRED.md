# STAR Ver.1.4 配備前の明示承認

2026-10-18更新: PR #21には既にBedrock/OpenAI共有通信を使う実AIアダプターと
出典照合付き`prose-v2`がある。最終runtime検証・Linux ZIPは`e53c1df`に固定されている。
下記の2026-10-10時点のFake-only記録は履歴であり、現在の実装を表さない。
現時点でも配備・実モデル品質/IAM/遅延/料金の実測は未実施。
実機用STARフロー、12品質ケース、18送信までの費用試算とClosure条件は
[実AIアダプター](STAR_V14_LIVE_ADAPTER.md#2026-10-18-限定公開前の実機検証手順)を参照する。
この更新はStage2正本や承認範囲を変更しない。

今回AWS接続、State操作、remote Plan、Apply/Destroy、Artifact upload、Lambda配備、実OpenAI、main merge、dev有効化を実行していない。現時点で配備・費用発生の承認を求める段階ではない。

将来、対象commit HEAD、Account/Region、Artifact SHA/version、費用上限、saved Plan SHA-256、資源差分、4有効化フラグと条件付き自動Closureを固定した別承認が必要。P4承認テンプレートとTerraform runbookに従う。partial failureでは再apply・手動修復をせずread-only診断で停止する。

## ソース候補差分

- 16 STAR APIルートは全JWT。PUTと`X-Star-Application-Id`のCORS許可を追加。
- APIはUSER領域のtransaction ConditionCheckと、全体quotaの正確な`SYSTEM#STAR_QUOTA`へのtransaction Put/ConditionCheckだけ追加。ADMINのkey-only読取りを維持。
- `star_assist_ttl_enabled=false`を既定とした任意TTL候補。承認後にNumber `expiresAt`を対象にする。dev/test入力から明示的に渡す配備変更は別レビュー。
- 既存Streams filter、Worker MaximumConcurrency=2、4有効化フラグ、provider選択・lockを変更しない。Lambda artifactは未作成・未upload。

## AWS/実AI未検証

実DynamoDBのtransaction競合、IAM実評価、GSI反映、Streams配送、Lambda/SQS/Recovery統合、TTL物理削除、Cognitoと実複数利用者、実測課金は未検証。Memory/SDK Stubber/mock provider試験を実AWS保証として扱わない。

STAR実AI adapter、WIF・認証、モデルの可用性/Structured Outputs品質、実token/価格、prompt injection耐性は未接続。`gpt-6-luna`は未検証候補のままであり、現在のSTAR実行はFake固定。Fake費用0は実AIの費用推定にならない。

上限20/600回は呼出し件数上限。実費はモデル・入出力token・利用料金から別途見積もる。30人Mockの時間はブラウザ/Memory性能であり、AWS性能Gateを変更しない。実AWS検証後はPASS/FAIL/inbox確認の成否にかかわらず、同時承認条件を満たすClosureを実施し通常終了状態をclosedとする。
