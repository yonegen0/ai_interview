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
