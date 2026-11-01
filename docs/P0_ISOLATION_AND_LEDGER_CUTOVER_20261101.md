# P0停止・隔離と独立ledger世代の切替条件（2026-11-01 JST）

正式statusは **RELEASE_HOLD**。この文書とオフライン判定の成功は、停止実施、
実効IAM、過去会計復元、配備、有料AI、公開の承認・成功を意味しない。
調査基準はmain `dd96e43acca7d38d572588824b417bc2758f5780`。
旧環境の「旧」は別の4関数が存在する意味ではなく、現在のdevの旧配備世代を指す。

## 1. 再利用する証拠と今回確定した範囲

保存済みの親・独立子Stateはbyte hashが一致する。devはserial24/77資源、bootstrapは
serial9/40資源。これは既存証拠の再利用であり、現在時点の実体読戻しではない。
bootstrapの歴史的identity採用不足は残る。新規AWS要求、State取得、Terraform init/plan/applyは0。
依存はPython3.14.9、既存uv.lock、Terraform1.14.9、bootstrap/test AWS6.64.0・dev6.65.0を維持。

既存125要求はユーザー引継ぎの累計。近接した保存レポートの71要求と42要求だけでは
全125件の独立再集計は完了しないため、欠けた12件を推測補完したり125件を再照会したりしない。
実請求額は未照会。既存見積枠を請求額・hard capへ読み替えない。

正確なARN、UUID、API ID、Role、Queue URL、固定State証拠のhashはprivate inventoryへ保存する。
公開リポジトリへAccount、State本文、private原本、認証情報、回答、ledgerを転記しない。
State外の資源と実効権限は未証明。既存のDisabled・近似Queue0・保存中6kind0・metrics欠測は
既存の観測として保持し、drain、過去課金0、外部writer0とみなさない。

## 2. 旧4関数・直接writer・起動経路

下表の業務別書込みはmainソースと保存policyの能力から整理したもの。
配備ZIPのsource SHAは未確定であり、旧版で全ての新会計規約が動くと保証するものではない。

| 旧関数 / 実行Role | alias / 保存版 | 既知の起動・書込み | 停止の影響 |
| --- | --- | --- | --- |
| ai-interview-dev-api / ai-interview-dev-api-runtime | live / 5 | HTTP API JWTルート→API。Session/Attempt/Evaluation/Dispatch、STAR予約、冪等性記録を同一main tableへtransactionで書く | 一般利用の保存・評価受付・STAR受付・参照の停止 |
| ai-interview-dev-admin / ai-interview-dev-admin-runtime | live / 3 | HTTP API管理ルート→ADMIN。質問bank変更のtransaction書込み | 質問bankの管理停止。通常の質問読取りとの共有に注意 |
| ai-interview-dev-worker / ai-interview-dev-worker-runtime | live / 5 | main SQS mapping→Worker。評価/STAR、処理権、共通会計の書込みと有料Provider送信 | 評価/STAR結果確定・会計記録の停止。処理中結果を失敗にしない事前保全が必要 |
| ai-interview-dev-dispatcher / ai-interview-dev-dispatcher-runtime | streams・recovery / 各5 | table Stream→streams mapping、Scheduler→recovery。Dispatch、Recovery cursor、状態遷移を書き、SQS送信 | 評価投入・再配送・lease回復が停止。未処理を新世代へ流さない |

Scheduler Roleは `ai-interview-dev-scheduler-runtime`。直接DynamoDB writerではないが
dispatcher:recoveryのInvoke権限を持つ。4関数の保存timeoutは15/15/60/30秒、reserved concurrencyは
未設定（State表現-1）。workerのasync invoke設定0件という既存観測は、async queue0の証明ではない。

既知の経路は、HTTP API→api/admin、DynamoDB Stream→dispatcher:streams→main SQS→worker:live、
毎分Scheduler→dispatcher:recovery→main SQS、SQS可視性切れ/部分失敗→再配送、Worker DLQへの移動、
Stream失敗Queueへの移動。DLQ手動redrive、CLI/SDK/Consoleからの直接Invoke/SendMessage/
DynamoDB書込み、別自動化、resource-based policy経由、既発行sessionからの呼出も排除対象。
後半の実在・主体・最終実行は未証明であり、ソースに無いことでは除外できない。

| Queue/寿命 | 保存構成 | 保全・再配送の扱い |
| --- | --- | --- |
| main | retention345600秒、visibility360秒、maxReceiveCount5 | Disabled mappingでも保持期限は進む。Receiveは可視性と受信回数を変えるためread-only調査に含めない |
| worker-dlq | retention1209600秒、mainのみredrive元を許可する設定 | 許可設定はredrive task不在の証明ではない。StartMessageMoveTaskは禁止 |
| stream-failure | retention1209600秒 | 失敗記録から原レコードを完全復元できるとは仮定しない |
| Stream mapping | record age3600秒、retry3、部分失敗応答、bisect | 無効化中もStream保持期限は進む。table内のDispatchとの照合・原本保全が必要 |
| Lambda native async | 明示設定の既存Worker観測0件、4関数のState上DLQなし | 非同期queueをSQSと同一視しない。列挙できないpayloadの保全は未証明 |

Lambda native asyncは標準でスロットル等を最大6時間再試行し得る。
reserved concurrency0は新asyncイベントを再試行せず失敗宛先へ送るため、宛先なしでの適用を
「保全付き停止」としない。[async再試行](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)、
[concurrency0の配送](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-retain-records.html)。

## 3. 資格情報・共有資源と誤停止防止

4関数は同一dev tableを使い、5aliasは同じ4関数・実行Roleを再利用する。
次のin-place配備は独立環境ではない。共有Boundary、Cognito、SES、State/Artifact bucket、
GitHub OIDC provider、旧/標準CI Roleを一括停止しない。
API無効化はexecute-api既定endpointの既存観測であり、別domain/直接Invokeの排除を保証しない。

| 主体・取得経路 | 既知の権限/影響 | 必要な排除証拠 |
| --- | --- | --- |
| Lambda→4実行Role、Scheduler→専用Role | 発行済み一時credential、service trustからの再取得 | 対象Role固定、資源限定Deny、trust閉鎖、旧sessionの失効と独立読戻し。共有Roleなら変更停止 |
| 旧CI artifact/plan/deploy/test、標準CI各Role→GitHub OIDC | deployはコード/alias/mapping/IAM/PassRoleを変更できる。直接writerと権限再取得を可能にする管理主体は分ける | devへの再Enablement、旧Roleへの権限復元、隔離guard削除を防ぐ管理経路。workflowを実行しないだけでは権限失効にならない |
| ローカルSSO/運用者、他session/外部自動化 | Stateに全permission set/発行済みsessionは存在しない | 固定主体への限定監査、または対象資源側の強制Denyと管理経路の封鎖。未知主体0とは報告しない |
| Bedrock/WIF/外部Provider | 旧Workerは保存構成でBedrock。直接API専用Secretは既存照会でABSENT | 既送信のProvider処理はLambda停止で取消済みにならない。外部token/開始済み送信の寿命・結果不明を別記 |
| Cognito access token | 利用者JWTはIAM実行credentialと異なる | ログアウトだけでLambda実行Roleや直接Invokeを失効できない |

AWSRevokeOlderSessionsはcutoff以前のsessionをDenyするが、cutoff後の再取得は止めない。
service trust閉鎖と継続的な対象権限Denyを組み合わせる。
全session失効はログ等も止めるため、記録・保全完了前に適用しない。
session cutoffの未来時刻を推測で決めたり、既存policyを上書きしたりしない。
[公式session失効](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html)。

## 4. 対象限定の停止手順と独立検証

下記は実行順序の設計。private packageの未成立前提をPASSへ置換するまで変更承認を求めない。
対象一覧に存在しない資源を動的に追加しない。API失敗、複数候補、ページ超過、差分逸脱、
結果不明では追加試行せず、その段階の証拠を保存して該当作業を停止する。

1. **実行固定**：source・inventory・各入力hash、Account/東京、操作者/独立監査者、期限、
   API別回数/SDK再試行0、費用見積枠、private ACLを固定。旧承認を再利用しない。
   保存されたStateを改変せず、今回の操作前条件に必要な対象だけを照合する。
2. **保全先行**：業務上の停止対象と共有依存、既発行権限、処理中リクエストを照合。
   table内の既存job/ledger、SQS3系列、Stream、native asyncの保全対象・hash・保持期限・
   復元方法を確定。近似0だけで省略しない。不可視payload/処理中結果の保全が証明できなければ
   concurrency0/書込み遮断/全session失効へ進まない。勝手なReceive/削除/再送/推論は禁止。
3. **流入封鎖**：対象API入口、Schedulerを停止状態へ固定。2つの既知mapping UUIDを
   EnabledからDisabledへ変更する場合だけ変更し、Disabledを読戻す。
   関数名filterでmapping0件だった旧失敗を繰り返さず、固定UUID/SourceArn/aliasの一致を確認。
   直接Invoke/SendMessage・redriveと管理経路は対象限定policyで封鎖する。
4. **実行停止**：保全条件成立後、旧4関数それぞれのreserved concurrencyを0へ。
   mapping/Scheduler停止だけで既存実行終了としない。最後の受理/開始、実行timeout、
   IAM伝播、native async寿命・失敗宛先と未完了Provider要求を照合する。
   metrics欠測や数分待機を独立証明の代用にしない。
5. **writer隔離**：対象4RoleのDynamoDB PutItem/UpdateItem/DeleteItem/BatchWriteItem/
   TransactWriteItems/PartiQL書込みを対象tableだけDeny。旧Workerの有料送信権限も対象限定で遮断。
   Scheduler Roleのdispatcher Invokeを遮断。旧service trustを閉鎖し、cutoff以前sessionを失効。
   共有Boundary全体・Account全Roleへの一括変更は禁止。
   旧Role以外のwriterには、table側のdeny-except-approved-principalsとそのpolicyを戻せる
   管理主体の制限が必要。新世代は専用Roleを使う。具体的policy bytes未レビューなら適用しない。
6. **独立読戻し**：別プロセス/独立監査者で、4関数concurrency、5aliasの版/weight、
   2mapping、API/Scheduler、Role trust/inline/attached/boundary、table側policyを読み戻す。
   policy simulatorの成功だけを実効IAM成功としない。必要な拒否試験は対象・無副作用方式を
   別途固定し、有料Invokeや利用者データ書込みを確認手段にしない。
7. **証拠封印**：操作ごとの開始/応答/結果不明、独立結果、hash、実要求数、保持期限を
   exclusive createで保存。未処理/OUTCOME_UNKNOWNを新規処理へ変換しない。
   新世代の入口は閉鎖を継続する。既存main成功CIを停止の実証へ読み替えない。

復旧は「有料旧環境へ自動復帰」ではない。部分失敗時は閉鎖と保全を維持する。
変更前policy/trust/hash、concurrency未設定状態、mapping/Scheduler/APIの値をprivate保存し、
隔離前と同じ安全条件が再成立した場合だけ対象限定の逆変更を審査する。
concurrency未設定の復元はDeleteFunctionConcurrencyであり、-1をPutへ送らない。
session失効のDenyを消すと有効期間内の旧credentialが再有効化し得るため、通常rollbackでは除去しない。
旧Alias/Queueを新世代に付け替えず、データ削除・purge・redrive・ledger resetをしない。

## 5. 過去ledger未復元時の代替案

現行mainのProviderUsageはUTC月だけでkeyを生成し、同じtableで評価/Coaching/STARを原子的に
予約する。eventVersion1のSQS本文にはledger世代がない。
**環境変数に世代名を追加するだけでは隔離できない。現行runtimeの独立世代対応は未実装。**
安全条件未確定のまま本番互換event/codecを変更しない。

採用候補は、専用の新table・新4関数Role・新Queue/Stream/mapping/Schedulerで構成する
閉鎖された独立service世代。既存single-table transactionを保持し、会計だけを非原子的に
別storeへ切り出さない。新資源名・ARN・費用・Terraform差分は正式設計/Plan承認へ固定する。
旧tableと履歴は保存し、Session/Attempt/Evaluation、質問bank、Cognito subとの関連を
破壊しない。必要データ移行は別の限定レビュー対象であり、旧pending/Dispatch/startedを
自動copyしない。移行対応未完了なら新環境の公開をブロックする。

必須条件：

- 旧Roleの新table/queue/secretへの明示Deny、新principalだけのアクセス、管理経路の封鎖。
  Role名だけの変更やshared boundaryのAllow削除だけでは未知writer排除を証明しない。
- 新旧Queue/Stream/SourceArnと世代を固定。旧message、DLQ、Recovery、idempotency keyは
  新世代で予約/推論する前に拒否・隔離。旧jobの完了を再送で推測しない。
- 新会計期間は**停止・全旧送信のsettlementが成立した後の完全なUTC月**。
  仮候補2026-12-01 00:00 UTC（09:00 JST）は、11月末までに隔離が実証できた場合だけ。
  遅れれば次の完全月へ繰り延べる。11月中に新空ledgerを作り20/600枠を再付与しない。
- 新ledgerの初期hash、generation、対象期間、初期0の根拠を独立確認。
  旧履歴が0だった意味ではない。旧過去請求と新期間の送信数を別の会計として記録する。
- 評価/Coaching/STAR、全Providerの手動切替を通算して月20/ユーザー・600/全体以下。
  原子的予約、同じjobの予約再確認、started後不明時の再送禁止、lease/Recoveryを維持する。
- 過去会計の未確定額・本人別回数・欠測/TTL/削除の影響を残余リスクとして明記。
  ユーザーによる具体的な受容記録が必要。受容しても過去会計をPASSにしない。
- 旧writer再出現、世代不一致、quota不整合、OUTCOME_UNKNOWN、証拠欠落、保持期限到来、
  予算/時間枠到来で新規受付停止。新世代の停止/復旧は保全済み同一世代へ限定し、
  旧ledgerへ戻して枠を再付与しない。

過去会計復元の代替は、過去リスク受容と未来期間の独立した安全証明である。
新世代を安全に運用する設計ができても、旧payload保全・外部Provider settlement・
新世代実装/実効権限が未証明ならP0解消ではない。

## 6. オフライン判定の使い方と限界

`backend/skills/p4/ledger_cutover.py` はpureな審査補助で、AWS/file/network/CLI操作をしない。
呼出者が検証したclaimを厳格schemaで受け、11隔離条件、証拠hash、正確なAccount/Region/ARN、
新旧table・Roleの分離、UTC期間非重複、20/600以下、世代fence/原子性/復旧、残余リスク受容を判定する。
履歴のUNPROVENは維持し、publication=NOT_EVALUATED、authorization=NONEを常に返す。
PASSのclaimには証拠hashを要求するが、hash内容の真実性・対象/時刻への適用性は独立監査者が確認する。
これは承認器・本番runtime guardではない。証拠の自己申告だけで実AWS受入へ進めない。

実行例（offline、合成fixture）：backendで
`uv run --locked --offline pytest -q tests/unit/test_ledger_cutover.py`。
実ARN/原本をテストfixtureやPR本文へ入れない。

## 7. 公開までの依存順序とGate

| 順序 / Gate | 現状 | 通過条件 |
| --- | --- | --- |
| A: 既存コード/CIと停止対象整理 | PASS（オフライン範囲） | 固定mainと保存証拠。私有inventory62資源。新旧関係を区別 |
| B: 保全・旧停止・全writer/権限再取得排除 | BLOCKED | native async/inflight保全、未管理writerと管理経路、対象限定policy/独立拒否証拠が不足 |
| C: 過去会計復元 | UNPROVEN | 完全ledger候補未特定。探索を反復せず保全 |
| D: 独立ledger代替 | BLOCKED | B成立、将来UTC月、新table/Role/SourceArn/世代fence/移行実装と実効権限、残余リスク受容 |
| E: Secret・Artifact・各正式Plan/Apply | NOT_RUN | BおよびCまたはD、bootstrap identity、実Secret ARN、固定Artifact/入力/Plan hash。PlanとApplyは別承認 |
| F: 実Claude・認証/本人分離・30人・運用受入 | NOT_RUN | 料金/回数/時間、監視、条件付きClosureを固定した有料試験承認 |
| G: Fake性能 | FAIL継続 | p95=2003.466ms > 2000ms。新しい原因識別証拠なく閾値/並列度/メモリを変更しない |
| H: HTTPS/CORS・監視通知・Recovery・最終公開 | BLOCKED | 実受入、依存Gate、明示公開承認 |

直接Anthropic Claude Haiku5.5採用、固定model/API version、Worker専用Secret、20/600、
Bedrock/OpenAI手動予備・自動fallbackなしはmainの方針/実装を保持。
[公式モデル](https://platform.claude.com/docs/en/models/overview)、
[API version](https://platform.claude.com/docs/en/api/versioning)を確認するが、実利用権・配備完了は未検証。
Issue #106は実AWS受入までOPEN。Issue #92は2 GHSA由来21 moderateの期限付き例外
（2026-11-15 09:00 JST）。PR #43のHOLDは維持し、toolchain更新やmergeを行わない。

承認は次に判断を変える不足証拠と安全な対象限定変更だけをprivate packageへまとめる。
正確なAPI/回数/費用/復旧と保全前提が固まらない変更は「実行可能な承認」と表示しない。
Secret/Artifact/Plan/Apply/有料検証/公開を、停止審査への一括承認に混入させない。
