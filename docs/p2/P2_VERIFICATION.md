# P2設計確認記録・P3試験引継ぎ

更新日: 2026-09-12。P2-202〜212の設計レビュー記録。
これはソース照合・文書検査・机上レビューであり、Backend試験/実DynamoDB/Streams/SQS/IAMの成功記録ではない。
P3実装未着手。依存追加・環境構築・コード/CI変更・ZIP展開・AWS操作・実AI呼出なし。

## 読み取った根拠と差分

- git status --shortを最初に確認し、frontend/AGENTS.mdを読んだ。未コミット変更を編集元とした。
- MemoryRepositoryのcreate_once/accept_once/next_once/3 GET/claim/finish、Applicationのfingerprint、
  Workerの明示呼出、公開Pydantic Schema、Frontend API契約を照合。
- 先行internal.py差分は属性追加だけでMemory/Worker未接続。現在acceptはDispatchを保存せず、
  claimはAttempt/None、finishはleaseを扱わない。これを設計完了と混同しない。
- 本人PK、元成功応答、Question snapshot巡回を維持し、全POSTの業務状態より先の冪等照合を引き継ぐ。
- 前草案の保存形式/命名/投影の不一致を解消: JSON＋rev、snake_case、KEYS_ONLY。
  毎回先頭のみQueryする案を、3つのCursorで中断位置を継続する方式へ修正。
- AWS公式資料を確認し、Transaction IAM action、SQS並列2の推奨との差、
  Streams filterがJSON内部を比較できるという誤解を補正。出典は各仕様本文に記載。

## 工程別決定・確認・引継ぎ

| 工程 | 決定内容と根拠 | 見送った案 | 確認 | P3/後続 |
|---|---|---|---|---|
| 202 | 5 Entity、immutable回答/snapshot、公開と実行状態を分離 | 現先行型初期値を仕様化、terminal再開 | 下記全状態/参照とR01〜R19 | 301 |
| 203 | USER PK、JSON＋rev、1 GSI/3 partition/KEYS_ONLY、Cursor | Map二重管理、初期shard、先頭だけ走査 | A01〜A17、9サンプル、R18 | 303/304/308A |
| 204 | T01〜T14のCASと非更新item条件確認 | 別active上書き、部分受付、DB障害を409化 | R01〜R16 | 305〜307 |
| 205 | 5件保存確認で202、Iがcommit証拠 | SQS成功待ち、短期tokenだけで冪等保証 | R03/R04/R17 | 306 |
| 206 | Dispatch＋Streams＋定期Recovery | API送信だけ、定期のみ、Pipes必須 | R05〜R08/R19 | 308B、AWS実配送P4 |
| 207 | 実行ID/leaseVersion、started marker、呼出予算50秒 | 期限切れ直接claim、startedから再呼出 | R09〜R14 | 307 |
| 208 | 関連→終端→deadline→状態の順、startedはunknown | 120秒で評価打切り、GET回復 | R07/R09〜R18/R22 | 308 |
| 209 | 60/90/40秒、15分、visibility360、並列2、各層retry境界 | SDKとRepoの二重retry、Provider自動再呼出 | R05〜R13、公式設定照合 | 308/P4負荷/P5 Provider |
| 210 | 合成データP3は自動失効なし、個人投入前Gate | 一律TTLで元応答消失 | R17/R20 | P4保持/本人削除 |
| 211 | R01〜R22障害表と監視/手動対応 | processing放置を成功扱い | 全R、全非終端の回復先 | 309/310/P4 Alarm |
| 212 | 信頼したsub、内部owner照合、実行role限定 | 管理権限流用、ログへ本文/Token | R08/R15/R19 | P4/P6実Token |

各仕様の詳細:
[Entity](entity-model.md) / [状態](state-machine.md) / [物理](dynamodb-design.md) /
[Transaction](transactions.md) / [ADR](../ADR-004-durable-evaluation.md) /
[保持・障害・権限](operations-and-security.md)。

## 机上レビュー（実行テストではない）

初期状態→操作/障害→更新→公開応答→禁止副作用の順で照合した。
以下は設計から導いた期待結果。各行の禁止副作用をP3でassertする。

| ID | 初期→操作/障害 | 更新と公開応答 | 禁止副作用/照合結果 |
|---|---|---|---|
| R01 | Iなし→同キー同要求2本 | 1 Tx、残りI読取り→同じ201/202/200 | ID/時刻再生成・2件作成なし。T01〜03整合 |
| R02 | 同S→別キー回答、Answer/Next、Next/Next | rev勝者後に再判定、現在条件不成立なら409 | 古いquestion/fromAttemptの適用なし。再評価後合法なら直列成功も可 |
| R03 | Iなし→Tx条件拒否/DB障害 | 全新規不在、状態再読取り→業務409または固定500 | 部分受付なし |
| R04 | 受付5件commit→応答消失 | I確認→元202、処理独立 | 受付不明を未受付と断定しない |
| R05 | PENDING→SQS成功→confirm保存失敗 | 先着claimまたはlease後再送、公開processing/終端 | SQS重複でProvider増殖なし |
| R06 | PENDING→Worker claim/finish→遅いconfirm | D DONE、confirm obsolete、GET completed | QUEUEDへの巻戻りなし |
| R07 | QUEUED→Worker起動なし | claim_due後世代+1、再投入→初回評価 | Attempt/Evaluation増殖なし |
| R08 | 現世代2→世代1/重複/順不同/隔離再投入 | stale/busy/terminalはack、現pendingだけclaim | 終端再開なし |
| R09 | running未開始→停止 | lease後pending・世代+1→新claim | 古いexecution開始不可 |
| R10 | started保存→実送信前停止 | lease後failed/EVALUATION_FAILED | Provider0回でもunknown扱い、勝手な再呼出なし |
| R11 | started→Provider処理中/成功直後停止 | 保存結果喪失ならlease後failed | 結果の再取得目的の再呼出なし |
| R12 | 結果保持→finish DB失敗/応答消失 | 同結果保存または終端確認→GET結果 | Feedback.createdAt変更/Provider再実行なし |
| R13 | WorkerとRecovery/Recovery同士が同rev観測 | CAS勝者のみ。期限後の旧start/finish拒否 | lease/generationの巻戻りなし |
| R14 | Sが別active/null→旧評価finish | S非一致ConditionCheck＋E/D終端 | 新active/number/version変更なし |
| R15 | owner/逆参照/関連欠落 | IntegrityError、更新なし、500/processing | Provider呼出・自動owner修正なし |
| R16 | 配送予定/leaseがdeadlineより後 | min dueでT13→failed | deadline後の再投入/呼出なし |
| R17 | UI自動確認120秒停止→手動再確認 | 元202固定、GETは最新。Backend継続 | 保存version変更、自動POST、UI停止でBackend失敗なし |
| R18 | 100件超/古い候補→途中停止/同時Recovery | base再確認、Cursor継続、次巡再訪 | 常に同じ先頭のみ処理しない、GSIだけで更新しない |
| R19 | 不正イベント/未知version | DB不変、batch失敗→隔離 | 公開状態追加・Provider呼出・生payloadログなし |
| R20 | 保存後→process/選定保存先再起動 | I/Feedbackを取得、startedは回復方針適用 | 保存期間リセット/Provider再呼出なし |
| R21 | Provider結果不正/過大 | 固定failed、reasonは内部のみ | 回答切詰め・Schema変更なし |
| R22 | DB/GSI障害中deadline到来→復旧 | 候補再走査→失敗収束 | 障害中の期限内確定を保証済みとしない |

全非終端の回復経路:
pending/PENDING→D index→配送またはdeadline、
pending/QUEUED→D index→世代更新またはdeadline、
running未開始/開始済み→E index→再投入/unknown/deadline。
破損参照は自動収束対象ではなくR15の監視/手動復元に明確に分離。
GETはどの経路も起動しない。

## P3で実行する具体試験

全R01〜R22を追跡する。共通suiteはRepository公開業務操作とFake時計/Publisher/Providerから観測する。
snapshot/_lock直参照の既存Memory試験はMemory専用に残す。

| 試験群 | 手順/境界 | 必須assert | 層/依存 |
|---|---|---|---|
| C01 6 API | 既存contracts/backend-fixtures.json全step、正常/不正/本人外/405 | status/body/Allow、error固定、Zod契約、GET Provider回数0 | Memory＋DB、304/309 |
| C02 回答 | 日本語、通常絵文字、単独surrogate、改行、JS空白、500/501 code unit、前後空白 | 原文同一、拒否時書込み0。通常下書き/旧pending互換は変更しない | Serializer＋共通 |
| C03 score/任意値 | 78/78.0/7.8e1、bool/string/null/小数/NaN/Infinity/範囲外、exampleAnswer省略/null | 整数78、他は固定評価失敗、null非出力 | Provider検証＋共通 |
| C04 冪等 | 各3 POST同時同キー、異本文/異Path、別owner同キー、完了/次問/再起動後 | 1更新/元Status/body固定、異要求409、別owner独立 | R01/R04/R17/R20 |
| C05 並列 | barrierで2 Repository・2 processから競合、Answer/Next、Next/Next、別キー回答 | 直列化可能な結果、部分保存なし。合法再判定と409を区別 | R02/R03、実DB必須 |
| C06 応答消失 | 各Tx commit直後に応答だけ落とす、commit前拒否、予算消費 | 元応答/terminal照合、ID/時刻/token方針、正常409へ偽装しない | R03/R04/R12 |
| C07 配送 | SQS失敗、成功直後停止、確認前Worker完了、古い世代/重複/順不同 | D巻戻りなし、現世代だけclaim、Provider最大初回1 | R05〜R08 |
| C08 停止位置 | claim後、marker前後、実送信前、Provider処理中/成功後、finish前後 | 未開始だけ再投入、開始後はunknown、DB保存のみretry | R09〜R12 |
| C09 時刻fencing | expiry-1ms/expiry/expiry+1ms、古い権利start/finish、開始残時間49999/50000ms | 期限切れ送信禁止、50秒未満呼出禁止、CAS勝者だけ適用 | R13/R16 |
| C10 回復 | queued起動漏れ、Recovery同士、別active、deadline逆転、DB長期停止 | T10〜T13整合、S保護、復旧後収束 | R07/R13〜R16/R22 |
| C11 Query | 各partition101件以上、旧候補/同sort key別owner、途中終了、checkpoint消失 | 完全キーでページ継続、後続到達、次巡で追加候補回収 | R18 |
| C12 Serializer | 9 snapshotのdecode/encode、整数/UTC/任意省略、350KiB境界 | data/原文/202一致、terminal indexなし、過大結果固定失敗 | R21 |
| C13 Security/ログ | malformed/unknown version/owner不一致/参照欠落、全障害でログ捕捉 | Provider0、固定分類のみ。本文/Prompt/Token/生例外なし | R15/R19 |
| C14 永続化 | 別processで書込→終了→読取、選定環境再起動（Local時はvolume維持） | 元201/202/200とFeedback、権利/世代が持続 | R20、実DB必須 |
| C15 CI/接続 | 明示endpoint欠落/誤設定、専用Table衝突、DB停止 | Local→AWS fallbackなし、試験未実行を成功扱いしない、他Table削除なし | 302/310 |

実DynamoDBが未選定/未実行ならC05/C14等は検証待ち。
Memory/Stub成功はDB Transaction保証を満たさない。実機をP4へ送る場合も未検証一覧を残す。
Localを選ばなかった場合はLocal起動/volume試験そのものを要求しない。
P4 Streams配送/SQS redrive/IAM/実Token/Alarm、P5実Provider、P6実Frontend接続、P7画像問題は別Gate。

## 文書検証結果

2026-09-12、設計・計画の12ファイル（Markdown11＋JSON1）を検査した。

| 検査 | 結果 |
|---|---|
| 相対リンク | 74参照すべて存在、欠落0 |
| Markdown | 全表の列数整合、コードフェンスの未閉鎖0 |
| JSONサンプル | 9状態・43 itemをparse。owner/参照/状態/期限/GSI/原文/元202等269チェック成功 |
| fingerprint | 3要求のv1正規化JSONをSHA-256計算し、全サンプルの保存hashと一致 |
| 机上レビュー | R01〜R22を状態表・T01〜T14・回復/監視へ照合。実行試験ではない |
| 進捗/環境表現 | P2設計確定、P3未着手。Local必須・P2の追加環境導入指示なし |
| 保護対象 | 開始時に取得したBackend/Frontend/契約/CIの67ファイルのSHA-256が終了時と一致 |
| Git | git diff --check成功。新たな追跡済み差分は決定事項文書のみ。他は既存未追跡文書の更新/追加 |
| 未実行 | Ruff/pytest/CLI/Frontend test/実DB試験。文書のみ変更のため今回再実行していない |

使用した確認方法: PowerShellのUTF-8読取り/ConvertFrom-Json/Test-Path/Get-FileHash、
既存tool内JavaScriptのJSON.parseによる状態assert、git diff --check。
新規Runtime・package・検証環境は不要だった。
再確認時は12文書の相対リンクを各親ディレクトリから解決し、sample-itemsの各dataもJSON decodeして
Entity参照、状態組合せ、min期限によるindex、全状態の同一冪等202を比較する。
サンプルのfingerprint_requestsは辞書順/ASCII escape/空白なしJSONをhashする。

Gitには既存cacheディレクトリへのアクセス拒否警告、LF/CRLF警告がある。
本検査対象文書の読取り/検査は完了。cacheの削除やignore修正で警告を消す操作はしていない。
既存Python/依存/lock/CI/内部モデルの先行差分は保持。ZIPはjava.zip=202,320,866 bytes、
dynamodb.zip=56,623,311 bytesで存在し、展開・実行していない。

以上からP2-202〜212は設計成果物・机上照合の完了と判定する。
P1成功件数を再実行結果へ流用せず、P3コードと実機試験の完了は別に証拠を求める。

## 引継ぎと停止条件

設計に必要な内部選択は上記文書で一本化した。追加Runtimeなしで実装仕様を説明できる。
本番保持日数/本人削除/Backup削除復元はP4実個人投入前、課金上限/実ProviderはP5呼出前、
Tokenと保存分離はP4/P6公開接続前の停止条件として残す。
P3開始時の検証環境選定は意図的な後続判断でありLocal必須へ戻さない。
先行した未検証コード/設定/環境/ZIPは [継続計画](../BACKEND_P2_P3_PLAN.md) 第5節に一覧化した。
P2完了後も自動でP3へ進まない。次の作業はユーザーからP3開始の指示を受けてから行う。
