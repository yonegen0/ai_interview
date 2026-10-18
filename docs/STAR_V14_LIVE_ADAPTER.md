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

## 構造化応答と事実性

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
