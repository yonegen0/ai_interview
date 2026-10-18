# STAR Ver.1.4 実AIアダプター

## 接続と設定

本番の`aws_runtime.build_entry("worker")`は、既存の明示Provider選択からSTAR専用
`LiveStarProvider`を生成する。標準構成はBedrock / Claude Haiku 5.5 / Tokyo / JP Geo
`jp.anthropic.claude-haiku-5-5` / Converse / adaptive thinking / low effort。
OpenAI予備は既存設定で明示切替した場合だけ使用する。Fakeはローカルdemoまたは既存の
owner制限付きvalidation構成だけ。本番の未指定Providerは従来どおり設定エラー。
API/Admin/DispatcherにはAIクライアントを構成しない。

`StructuredPrompt`でSTAR用データ・schema・2048出力token上限を渡し、既存のBedrock/OpenAI
送信・認証・応答解析・拒否/不完全/不確定送信の分類を再利用する。STAR専用API通信実装はない。
通常評価のschema、30点Coaching V2、V1互換、既存Provider設定は変えない。
STAR入力予算はinstruction/data/schemaのASCII JSONで24000 bytes以下、出力2048 tokens固定。
Provider/モデル/effort/STAR version/token/input上限をProvider IDへ含め、claim時に永続固定する。
料金のhard capではない。STARは独自の20/600 JST暦月予約・消費を使い、通常評価の
100/3000 UTC暦月ProviderUsageを参照・変更しない。実行権限はPR #20のWorker専用権限と同じ。
AWSへの設定・IAM適用、実推論、配備は別工程であり、この変更からは実行しない。

## 自然文モード（prose-v2）と原文互換モード

標準の`LiveStarProvider`は`prose-v2`。一回のモデル応答でA/B/Cの文章と
`passages[{source: S/T/A/R, text}]`を返させる。Aは結果から、Bは本人の行動から、
Cは状況から始める。Aは簡潔な丁寧語、Bは行動中心の改まった表現、Cは口頭向けの
説明調とし、構成順だけでなく文末と導入句も変える。150〜220コードポイントは目標で、
短い経験は水増ししない。導入句を含め最大400コードポイント。

創作防止は**閉じた言い換え規則と全文出典照合**による。サーバーが各入力項目から
許可済みの文章候補を導出し、モデルは内容の十分性・応募先との適合を判断しながら
その文章と構成を選ぶ。例えば「確認することができました」→「確認できました」、
「共有を行いました」→「共有しました」、過去の「共有した」→「共有しました」／
「共有いたしました」／「共有したんです」。未対応の表現を自由文として通さない。
引用や名称を述べる記述は変換しない。否定形の変換には専用の対応を用いる。

全ての非空S/T/A/Rを各案で一度ずつ参照し、各項目内の文順・主語・数値・期間・
固有名詞・否定・条件・不確実性を削除しない。モデルの参照先が正しくても、本文が
対応する許可表現と一致しなければ採用せず、追加情報へ返す。応募先や質問は出典に
できない。モデルの追加質問も未確認の実績を前提にし得るため、その自由文は表示せず
中立なサーバー定義の質問に置き換える。入力とProvider versionは既存Generationに保存され、
出典対応と変換は保存入力から再導出できる。Public API／保存形式は変更しない。

長文は許可規則で冗長表現を圧縮する。原文400字超でも全案が400字以下なら生成可能。
意味内容を捨てる任意の抜粋・自由要約は許可しない。安全に収まらない場合は送信せず
整理を依頼する。最低1項目から送信を試行でき、本人行動Aがないready応答は追加質問に
変換する。明示的な同一文の肯定／否定の矛盾は事前検出し、一般の曖昧性・矛盾はモデルへ
確認判断を指示する。日本語の意味一致・矛盾検出の完全保証はしない。

送信する同一文章候補は`AB`などの共通キーへまとめ、原文・文章候補・schema・指示を
含め既存24000 bytes上限を維持する。2048 tokens、一回送信、Worker60秒／Provider40秒、
quota・Recoveryは変更しない。Provider IDの`prose-v2`と`grounded-v1`を分離し、
旧版で開始済みの処理を新版として再実行しない。

これは任意の自然文を意味推定だけで受け入れる方式ではない。未対応語彙の自由な言い換え、
情報選択による一般的な長文要約、自然さ・具体性・応募先適合性の品質合格は未達として区別する。
実モデル／人手評価は未実施。Mockで規則・拒否・文字数が通ることと、実回答品質は別である。

`LiveStarProvider(..., mode="source")`で旧原文保持方式を明示的に使用できる。
失敗時の自動fallbackはない。以下はこの互換モードの仕様。

## 原文互換モードの構造化応答と事実性

生成応答は`GenerationPlan`：status、candidates、missingInformationをすべて必須とし、
未知キー・不正JSON・重複JSONキー・非有限数・型不一致を拒否する。
candidateはid/style/fieldsを持ち、fieldsはS/T/A/Rの列挙値のみ。
型検証の後で、A/B/C順・style対応・重複なし・空メモ参照なし・本人行動Aの存在・
全入力項目の保持・結論/行動/会話の先頭項目・400コードポイントを意味検証する。
needs_informationは候補なし・1〜4件の非空質問に限定する。

創作防止の初期方式は**原文保持の構成生成**。実モデルは質問・応募先カテゴリ・業界を見て
構成順または追加質問を判断するが、回答本文はサーバーがメモ全文から組み立てる。
企業名・業界・モデルの自由文を本人実績へ混ぜない。否定や条件を切り取らず、全入力項目を
保持する。行動不足または全メモ合計400字超過では追加情報を求め、送信しない。
この方式は自由な言い換え・要約を提供しない。長文メモの圧縮や自然さの改善は残課題。
原文保持検査は出典保全の検査であり、本人の事実の真偽、モデルの理解、回答品質の保証ではない。

承認後の品質評価では、各styleの目的適合、応募先への適合、否定/条件の保持、
事実不足時の質問、命令混入への耐性、自然さを人手で評価する。
成功/失敗・数値・固有名詞・否定・曖昧/矛盾・400字境界の固定ケースを用い、
出典違反0を必須にする。今回のMock合格を実モデルの品質評価と置き換えない。

## 一回送信・deadline・Recovery

STAR claimはProvider IDをPREPAREDに固定し、startは同じlease/Provider IDを照合する。
永続STARTEDと独立quota消費の確認後だけ1回呼ぶ。開始後の再配送/Recoveryは再推論せず、
送信不確定/timeoutはOUTCOME_UNKNOWN、拒否/不完全/schema不正はFAILED_AFTER_START。
開始後は自動返金しない。前処理/owner制限の失敗はFAILED_BEFORE_START。

Worker60秒、Provider40秒、Concurrency2を維持。STARはlease/job/Lambda残時間から
保存用10秒を残した単調時計deadlineを渡す。Bedrockの既存guardはclient構成後と
署名後before-sendで35秒の余裕を確認し、connect3/read30秒、SDK送信最大1回に制限する。
応答後とSTAR意味検証後にもdeadlineを確認する。OpenAIは既存transportが実socket送受信で
残時間を設定する。BedrockのI/O timeoutは壁時計の強制中断ではなく、実環境で40秒以内に
必ず完了する保証はしない。絶対時間・実効IAM・実モデル品質/遅延は承認された実機試験が必要。

## 確認した一次資料（2026-10-18）

- [AWS Haiku 5.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html)：Converse/JP Profile、structured outputs非対応。
- [Anthropic Haiku 5.5 migration](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide)：adaptive thinking/effort、Bedrockではschemaをpromptに記述してローカル検証。
- [Boto3 Converse](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html)：system/messages/inferenceConfig/additionalModelRequestFields。
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)：既存Responses通信でSTAR schemaを渡す。

固定lockのboto3/botocore 1.43.93のConverse service modelに、STARリクエストを実際に
渡してSDK入力shapeをオフライン検証する。追加モデル固有フィールドのサービス受理は
公式モデル資料で確認しており、SDK shape検査だけでサービス受理や権限成功を主張しない。

## Stage2復旧後の統合順序（実行せずローカル検証）

#21は#19をbaseとし、#20のWorker専用Bedrock IAMも既存基準commitへ含む。
#21にはこれに加えてSTAR quota用DynamoDB権限・データ・認証の変更があるので、
#20とのTerraform差分がゼロだとは説明しない。今回のprose-v2変更はTerraformに触れない。

固定main拘束の解除と必要な審査後、#19 → #20 → #21の順を推奨する。
今回、隔離した監査用bare repositoryへ既存commitのコピーだけを読み込み、
#19 `7cafa485`＋#20 `f17ffd97`の仮想mergeを作り、それと旧#21 `495e217`を
`git merge-tree --write-tree`で検証した。両段階とも競合なし。
これは履歴にpublishされないlocal objectであり、mainや既存branchをmergeしていない。
旧#21に既に入ったIAM変更が、#20統合後も機械的な競合を作らないことの検査である。
実際の統合時は最新HEAD/base・必須CI・レビュー・保護を改めて確認する必要がある。

#19/#20統合後に#21へ最新mainを通常mergeし、baseをmainへ変更して残差分をレビューする
方法ならforce pushを要しない。これらのbranch/base変更は今回は実行しない。
差分分割をする場合もIAM前提を失わないか局所的に確認してから別途判断する。
AWS実効権限や配備可否はGit mergeの成否では確認できず、別の承認工程に従う。

## 2026-10-18 限定公開前の実機検証手順

この節は準備であり実AWS成功・有料推論・配備の承認ではない。
`backend/skills/p4/coaching_live.py`のCLIは従来どおり準備専用。
追加した`star_flow`は、承認後のoperatorが既存`auth_e2e.Api`と
`run_with_closure`へ接続する関数で、資格探索や有料実行CLIを追加しない。

フローは2本人のAPIから、session/question/context、空回答下書き、STAR下書き、
generation、3案保存、再読込み、選択前編集、明示Apply、回答復元、明示正式送信、
非同期評価完了まで確認する。正式送信は`X-Star-Application-Id`を付け、
`AnswerAssist`への紐付けを保持する。Applyだけでは通常評価を開始しない。
QUEUED/PREPARED/STARTEDをGETでpollし、NEEDS_INFORMATION/失敗/OUTCOME_UNKNOWNでは
通常評価へ進まない。書込みの失敗・結果不明は再送しない。同keyの冪等再現確認は
成功応答が確定した操作だけに限定する。本文・JWT・OTPをjournalへ保存しない。
新規IDは記録するが、データ全件scan/deleteや独自のAWS修復は行わない。

### 固定品質ケースと合否

`contracts/star-quality-cases.json`の12ケースを`star_corpus()`で展開する。
通常、1行動、数値/名称、曖昧な成果、否定/条件、本人行動不足、応募先カテゴリ、
表現差、矛盾、命令混入、導入句込み400/401コードポイントを固定した。
境界の絵文字はコードポイント計数用で、自然な回答品質を採点する題材にはしない。
400/401のrecipeもこの関数で展開し、入力をその場で差し替えない。
入力事実と異なるモデル回答の拒否は既存`test_star_prose.py`の
数値・否定・条件・雇用先・因果・感情の改変ケースを再利用する。

実機ではraw結果を非公開に保全し、採用前のモデル文章とサーバー採用後文章の
両方を入力に照合する。出典外の主張/条件欠落は1件でもFAIL。
通常・数値/名称・style-richの3ケースはreadyを必須にし、全件を追加質問へ返して
品質合格とはしない。他のケースもready率と追加質問の妥当性を別々に報告する。
missing-action/contradiction/401は追加質問を期待する。
日本語自然さ・話しやすさ・具体性・A/B/Cの差・応募先適合は人手で各1〜5点、
通常とstyle-richの全案について各項目3点以上を暫定受入基準とし、実行前に固定する。
未記入は未評価。Mockの規則適合、固定SDK shape成功、機械的な文章差だけでは
これらの人手品質や実サービス受理をPASSにしない。

### 承認時に固定する実行量・費用・終了条件

最初のdev smoke/品質batchは、STAR最大12送信と通常評価最大6送信、計18送信を提案する。
STAR通常ケース1件を`star_flow`に兼用し、その正式評価1件、別sessionでCoaching最大3深掘り
（初回+3回）と明示retry_attempt1件で通常評価最大6件。自動再試行/追加品質再測定0。
実際には矛盾/401はローカル拒否なので送信を減らせるが、その枠を別入力へ振り替えない。
同keyの成功再現GET/POSTは新しい推論を発生させないことを台帳で照合する。
モデルごとのresponse input/output tokens（thinkingを二重加算しない）、単調時計時間、
API端点/ARN/alias/Artifact SHA、Provider version、送信前の残枠を非公開台帳へ記録する。
usage欠測・結果不明・初回出典違反・予算余裕不足では残りの新規送信を停止する。
開始済み分は自動返金せず、Recoveryは再推論しない。

出力は各2048 tokens、STAR完全送信JSON24000 bytes、Provider原則40秒、Worker60秒、
concurrency2を維持する。バイト数から正確な課金token数は断定できない。
品質smokeの計画入力6000 tokens/送信と出力2048 tokens/送信を仮定すると、
18回の費用式は`18 * (6000 * input_rate + 2048 * output_rate) / 1000000`。
参考の[Anthropic公式単価](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
（100k以下、入力$0.10/出力$0.50 per MTok）と
[地域エンドポイント10%加算](https://platform.claude.com/docs/en/about-claude/pricing#cloud-platform-pricing)
を仮定した試算は約$0.0322、2倍の余裕で約$0.0644＋税。
これはAWS JP Geoの見積確定値でも請求hard capでもない。
[AWS公式料金](https://aws.amazon.com/bedrock/pricing/)の動的な該当行を今回のテキスト取得では
確定できなかったため、承認時にJP Geo/Standard単価と価格日付を固定することを残す。
Lambda/API Gateway/DynamoDB/SQS/Cognito/CloudWatch等の検証費用は別途合算する。
公開後の20/600・100/3000暦月quotaは、この有限batchの送信台帳を代替しない。

対象はAccount835384817629/ap-northeast-1の承認済みdevだけとし、実際のAPI、Cognito
pool/client、DynamoDB、SQS/DLQ、Worker role/alias、2 mapping、Scheduler、Alarm一覧は
State/manifestの承認済み読戻しで固定する。値が未確定のままenable/applyしない。
IAMはprofileとTokyo/Osaka modelの限定Allow、Worker境界opt-in、API/Admin非付与を確認する。
承認後の`GetInferenceProfile`、組織SCP/Boundary/実効権限確認はオフライン検査と区別する。

Enablementと条件付き自動Closureは既存`P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md`にまとめる。
試験PASS/FAILやinbox未確認に関わらず、成功apply後にState/実体が正常なら証跡保存後に
閉鎖する。4フラグfalseと今回Alarm削除だけ、最新Artifact/version/aliasは保持する。
partial failureでは再apply/手修復せずread-only診断で停止する。`run_with_closure`へは
この監査済みClosure実行・独立読戻しcallbackを渡し、ダミー成功辞書を実機証跡にしない。

### Cognito・E2E・性能の残る確認

既存37 Mock E2Eと665 frontend試験は入力不変なら再利用する。
`practice.spec.ts`は通常/再挑戦/次問/結果直リンク/応答消失/processing復元、
`coaching-v2.spec.ts`は3深掘り/履歴/下書き/失敗retry、`star-assist.spec.ts`は
3案編集/反映/復元/本人切替/競合、`question-management.spec.ts`はUSER/ADMIN分離をカバーする。
quota20/600と100/3000、Recovery、SQS重複配送は既存Backend回帰を再利用する。
実Cognito EMAIL_OTP/refresh/logout/期限、実JWT USER/ADMIN、2本人の実DDB/IAM分離、
GSI/Streams/SQS/Recovery配送、実ブラウザからの公開設定・CORSは未実施のまま残す。
現在のPlaywright設定はlocalhost Mock専用で、実機E2E成功と表示しない。

既存性能解析のCはp95=2003.466ms（FAIL）、30評価完了9.283秒はFakeのみ。
Init約1.3秒と初回構成等約0.42秒がcold tailの有力要因。warmupでcoldを除外して
元GateのPASSに変更しない。次回は同じC母集団でcold/warm、POST/poll、client/Gateway/
Lambda初回構成を分けて観測する。memory512MiB、concurrency2、PCなしを維持して先に測る。
30評価30秒の実AI達成は未確認で、2 Workerでの実推論時間を測るまで保証しない。
性能用30人Fake試験と上の有限品質batchは分け、実AI30件負荷は別の費用承認対象とする。
