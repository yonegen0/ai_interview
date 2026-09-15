# P2-203 物理保存・Access Pattern

状態: 設計確定（2026-09-12）。[Entity辞書](entity-model.md)を物理化する。
検証環境の選定・構築はP3-302。ここではDBへ投入しない。

## 保存形式の決定

| 比較 | 属性Map | JSON payload＋rev |
|---|---|---|
| 条件式 | 状態・時刻を直接指定可能 | 読取り時に業務検証、同じrevでCAS |
| 型変換 | nested型・Decimalと不正surrogateの個別処理が必要 | ensure_ascii JSONでJS文字列のcode unitも保存可能 |
| デバッグ | コンソールで展開しやすい | dataをJSON decodeする必要 |
| 更新 | 部分更新可能 | item単位で置換、書込み量は多め |
| 二重管理 | 条件対象とdomainのMapperが必要 | 業務情報はdata一箇所。indexのみ派生 |

JSON payload＋revを採用する。現契約の任意項目省略・原文・UTF-16 surrogateを損なわず、
既存copy-on-writeの境界をCASへ対応付けられるため。Map案を実装選択肢として残さない。
状態をトップレベルにも重複保存しない。条件式はrev、事前検証はdecodeした状態という組合せで実現する。
GSI以外で本文検索/部分更新は不要。将来の大きな項目更新負荷は運用再評価事項。

## 物理item辞書

全itemはDynamoDB native属性（低水準SDKではS/Nへ変換）で次を持つ。

| 属性 | 型・必須 | 初期/更新主体・整合 | 公開/機密 |
|---|---|---|---|
| PK | string/必須 | Mapperで生成、不変 | 非公開/owner由来 |
| SK | string/必須 | Mapperで生成、不変 | 非公開/ID由来 |
| kind | string/必須 | Session/Attempt/Evaluation/Dispatch/IdempotencyRecord/RecoveryCursor、不変 | 非公開 |
| schema_version | integer/必須 | 1、不変。未知版は失敗し黙って解釈しない | 非公開 |
| rev | integer/必須 | 新規0。全置換で旧rev+1。削除・再作成なし | 非公開 |
| data | string/必須 | Entity辞書全属性のJSON。状態更新主体だけ置換 | 非公開/Entityによる |
| work_pk | string/任意 | 非終端作業のindex partition。対象状態更新時に導出 | 非公開 |
| work_sk | string/任意 | 下記dueを導出。work_pkと同時存在/除去 | 非公開 |

JSONはsort_keys=true、ensure_ascii=true、allow_nan=false、separators=(',',':')。
scoreは公開検証後に整数化、Decimalは整数ならintに変換し他は保存schemaで拒否。
日時はdata内T整数。公開Feedback.createdAtだけZ文字列を固定保存する。
任意項目は省略、Session.active=nullは必須。JSONをdecode→encodeしても原文code unitは同一にする。
Session.versionは業務番号、revは全itemのCAS番号。Sessionでは初期0、業務更新で両方+1。

| Entity | PK | SK |
|---|---|---|
| Session | USER#<sub> | SESSION#<id> |
| Attempt | USER#<sub> | ATTEMPT#<id> |
| Evaluation | USER#<sub> | EVALUATION#<id> |
| Dispatch | USER#<sub> | DISPATCH#<evaluationId> |
| IdempotencyRecord | USER#<sub> | IDEMPOTENCY#<key> |
| 回復走査位置（補助メタデータ） | SYSTEM#RECOVERY | CURSOR#<work partition suffix> |

IDの大文字小文字・subは変更しない。UUID/key検証は現契約。新規生成ID衝突は500であり上書きしない。
前方検索で本人以外を探さない。履歴/お気に入り用GSIは追加しない。

## Access Pattern対応表

全直接取得はGetItem(ConsistentRead=true)。関連可変itemを同時観測する内部処理は
IDを解決してからTransactGetItemsで再取得し、関係を再検証する。
単独Getの連続だけで別時点の状態を「破損」と判定しない。
公開FeedbackのAttemptは不変なのでAttempt→Evaluationの2 Getでよい。
GSIは結果整合しか使えない。[AWS読取り整合性](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)

| AP | 操作/検索条件 | 必要item・属性/期待件数 | 物理操作/ページ |
|---|---|---|---|
| A01 | Session作成 | 同キー記録0/1、指定カテゴリsnapshot | Get→T01/なし |
| A02 | Session GET | 本人Session全data、1 | Get/なし |
| A03 | 回答/再挑戦 | 記録0/1、Session全data、1 | Get→T02/なし |
| A04 | 評価GET | 本人Evaluation状態・error、1 | Get/なし |
| A05 | Feedback GET | Attemptと関連Evaluation全data、各1 | 2 Get/なし |
| A06 | 次問 | 記録0/1、Session全data、1 | Get→T03/なし |
| A07 | 全POST再現/commit不明 | owner＋key、hash/reply、0/1 | 強整合Get/なし |
| A08 | claim | E/D/AとSession、各1。owner/関連、rev、状態、設定 | GetでID解決→TransactGet→T04/なし |
| A09 | 開始記録/不明確認 | E/D、各1。lease/started/deadline | TransactGet→T05/なし |
| A10 | finish/競合再確認 | E/D/A/S、各1。lease・active・結果 | TransactGet→T06/なし |
| A11 | 送信予定到来 | PENDINGのdue<=cutoff | WorkIndex Query→E/D再取得→T07/継続キー |
| A12 | claim未確認（201への追加） | QUEUEDのdue<=cutoff | 同Query→E/D再取得→T10/継続キー |
| A13 | stale Worker | RUNNINGのdue<=cutoff、call_phaseで分類 | 同Query→E/D/A/S再取得→T11/T12/継続キー |
| A14 | 全非終端deadline（追加） | 上記3 partition。各dueはdeadline以下 | Query→T13/継続キー |
| A15 | 送信成功/失敗確認 | E/D、各1、現世代/送信権 | TransactGet→T08/T09/なし |
| A16 | Recovery競合/古い候補 | 現E/Dと必要ならA/S、各1 | TransactGet→条件付き更新/なし |
| A17 | 回復走査位置の継続 | partitionごとのCursor 0/1 | Get→CAS Put/なし |

E=Evaluation、D=Dispatch、A=Attempt、S=Session。全書込み仕様は [Transaction](transactions.md)。
GETでは配送・claim・回復を起動しない。他ownerのIDは既存404。関連破損は固定500と安全な監視通知。

## WorkIndexとdueの定義

GSI名WorkIndex、partition key=work_pk、sort key=work_sk、projection=KEYS_ONLY。
work_skは13桁0埋めepochミリ秒＋'#'＋evaluationId。時刻は0〜9999999999999に制限する。
IDは同値sort keyが別ownerに存在し得るため、ページ位置には完全なLastEvaluatedKeyを使う。

| base item/状態 | work_pk | due |
|---|---|---|
| Dispatch PENDING | WORK#DISPATCH_PENDING | min(deadline_at, max(next_at, send_expires_atがあればその値)) |
| Dispatch QUEUED | WORK#DISPATCH_QUEUED | min(deadline_at, claim_due_at) |
| Evaluation running | WORK#EVALUATION_RUNNING | min(deadline_at, lock_expires_at) |

pending Evaluation、CLAIMED/DONE Dispatch、terminal Evaluationはindex属性を持たない。
claimはDから除去＋Eへ追加、未開始回復はEから除去＋Dへ追加、finishは両方除去を同一Transactionで行う。
期限が配送予定やleaseより先でもdueを遅くしない。
GSI伝播遅延中は一時的に候補欠落/重複/旧状態があり得る。条件付きbase更新だけを根拠に実行する。
DBまたはGSI障害中の期限内回復を保証しない。

## ページングと飢餓防止

Queryはwork_pk一致＋work_sk<=13桁cutoff+'#~'、昇順、Limit=100、FilterExpressionなし。
各回は3 partitionを1ページずつround-robinし、残り5秒で新規処理を停止する。
毎回先頭へ戻る案は、同じ破損itemが先頭を占めた場合に後続が進まないため見送る。
単一Tableに最大3件のRecoveryCursorを設け、ページ内の最後に判定を終えたキーをCAS保存する。
これは業務Entityではなく配送起動権でもない。追加RuntimeやQueueは不要。

Cursor.dataの全属性（全て非公開、Dispatcherのみ可変）:

| 属性 | 型/必須 | 初期・整合 |
|---|---|---|
| partition | string/必須 | 対象work_pk、不変 |
| cutoff | T/必須 | 新しい走査開始now。走査中固定 |
| after | Key Mapまたはnull/必須 | null。完了判定した最後の候補のPK/SK/work_pk/work_sk |
| cycle_started_at | T/必須 | 走査開始now |
| updated_at | T/必須 | checkpoint時now |

ページの終端まで処理したらLastEvaluatedKeyへ進む。途中停止なら最後に処理したitemの完全キーを保存する。
終端到達時はafter=nullとして次回cutoffを更新、新しく入った古いdueも次巡で拾う。
DB障害なら未処理候補を飛ばさずそのpartitionを中断。他partitionは予算があれば進める。
整合性破損は安全なIntegrityError計測後その候補を「判定済み」として進み、次巡で再検出する（業務状態は変更しない）。
同時RecoveryはCursor.rev競合なら負け側はcheckpointせず終了。業務更新の重複はE/DのCASで防止。
Cursor応答消失は再読取り。checkpoint失敗時の再処理は安全。
走査1巡が3分を超えたらRecoverySweepLag警報。全巡が完了しない過負荷を「回復保証」と呼ばない。
P4負荷試験で3分内に巡回できない/スロットルが持続する場合に限り、予算・容量・shard/time bucketを再設計する。
初期shard/bucketなし。GSI欠落が疑われる手動整合監査は別承認の運用作業で、APIへScanを追加しない。

## サイズとサンプル

全物理itemを保守的に350KiB以下で事前検査する。
ASCII JSONとしてのitem全体（属性名・dataのエスケープ・index含む）を計測するため、400KB制限に余白がある。
5件受付は最大1.75MiBでTransaction上限にも余白を持つ。
大きすぎるSession snapshotは受付前500。大きすぎるProvider FeedbackはRESULT_TOO_LARGEの固定失敗へ変換する。
原回答・公開Schemaの上限を変えず、結果の切り詰めも行わない。
DB由来の他のValidationExceptionをサイズ超過と推測しない。
[AWS Transactionの制限](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)

[sample-items.json](sample-items.json)は9状態の文書検証用native item集合。
dataは全てJSON文字列で、epoch・rev・GSI・元202の固定を示す。DB投入用seedや契約fixtureの置換ではない。
確認R01〜R19、P3-303/304/308Aへ引き継ぐ。
