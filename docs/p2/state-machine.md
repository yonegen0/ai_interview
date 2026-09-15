# P2-202 状態遷移・競合条件

状態: 設計確定（2026-09-12）。[確認記録](P2_VERIFICATION.md)のR01〜R19で机上照合した。
[Entity](entity-model.md)と[依存追加方針](../DEVELOPMENT_DEPENDENCY_POLICY.md)を参照。
コード・環境の変更は行わない。具体的な一括更新・CAS条件は[Transaction仕様](transactions.md)のT01〜T14。

## 公開状態と内部状態

| 公開Evaluation | Worker | call_phase | Dispatch | 備考 |
|---|---|---|---|---|
| processing | pending | not_started | PENDING/QUEUED | 未実行。配送確認と受信は競合し得る |
| processing | running | not_started/started | CLAIMED | 有効leaseのWorkerだけ開始・確定可能 |
| completed | terminal | started | DONE | Feedbackあり |
| failed | terminal | not_started/started | DONE | 固定error。開始前deadline超過も含む |

Session自体の終了状態は設けず、active=nullまたは公開Attempt状態を保持する。
OUTCOME_UNKNOWNは内部理由。公開はfailed＋EVALUATION_FAILED。DLQは配送側の隔離であり公開状態ではない。

## 操作別の許可遷移

| 操作・主体 | 確認事項 | 変更対象・結果 | 競合・不成立時 |
|---|---|---|---|
| Session作成/API | 主体・入力・キー、成功記録なし | Session作成、元201記録 | 同キー同要求は元応答、異要求409 |
| 回答受付/API | 冪等照合後、owner・現在question・非processing | Session.active更新、Attempt/Evaluation/Dispatch作成、元202記録 | 同キーは再現、別キー処理中は409。部分受付なし |
| 次問/API | 冪等照合後、現在activeがcompletedかつfromAttemptId一致 | number増分、active=null、元200記録 | 古いAttempt・非completedは409 |
| 再挑戦/API | completed/failed、現在question一致、新キー | 回答受付と同じ。番号維持、旧結果保持 | 処理中は409 |
| GET/API | owner・対象の存在 | 保存済み状態のみ取得 | 本人以外は既存404、未完成Feedbackは409 |
| 送信権取得/Dispatcher | PENDING・予定時刻到来・送信leaseなし/期限切れ、現generation | Dispatchに送信tokenと期限 | 他Dispatcherが取得済みなら変更なし |
| 送信成功確認/Dispatcher | 現generation・token・PENDING | DispatchをQUEUED、確認時刻とclaim確認期限 | CLAIMED/DONEや世代更新後なら巻き戻さない |
| 送信失敗・不明/Dispatcher | 現generation・token・PENDING | PENDING維持、次回時刻設定 | 旧送信者の更新は拒否。再配送重複は許容 |
| claim/Worker | owner/参照一致、現世代PENDING/QUEUED、pending、deadline未到来 | Evaluation running・新leaseVersion/token、Dispatch CLAIMED | busy/terminal/stale/missing/deadline_dueを区別。DB障害は例外 |
| Provider開始/Worker | running、leaseVersion/token一致、lease/deadline未到来、未開始 | Evaluation.call_phase=startedを永続確認してから呼出 | 処理権喪失なら呼ばない。保存不明は読取り確認 |
| 完了・失敗/Worker | running、現leaseVersion/token、期限未到来 | Evaluation終端、Dispatch DONE、現在Session.activeのstatusを一括更新 | 他activeは保護。旧leaseは拒否、既存終端は上書きしない |
| QUEUED回復/Recovery | 確認期限超過、Evaluation pending、deadline未到来 | Dispatch世代増分、PENDINGへ | claimと競合したら再判定し、runningを戻さない |
| 未開始停止回復/Recovery | running、lease期限切れ、not_started、deadline未到来 | Evaluation pending、処理権失効、Dispatch世代増分・PENDING | 開始記録/finishとの競合は再判定 |
| 結果不明回復/Recovery | running、lease期限切れ、started、終端未保存 | failed/OUTCOME_UNKNOWN、terminal、DONE、現在active同期 | 保存済み終端を優先。同Evaluationを再呼出しない |
| deadline回復/Recovery | 非終端、deadline到来 | failed/DEADLINE_EXCEEDED、terminal、DONE、現在active同期 | terminalなら変更なし。他回復と競合なら再判定 |

期限到来はnow>=期限、有効はnow<期限。非終端に対する回復はdeadline到来を優先する。
候補検索の結果だけで変更せず、対象の現状態と処理権を更新時にも確認する。
Session非一致時は非一致が維持されていることも一括確定の条件にする。
Provider開始前の入力/Prompt準備失敗も、正当なWorkerの失敗確定として扱う。
Provider出力が戻りDB保存だけ失敗した場合は、同じ結果の保存だけを再試行する。

## 禁止・不明ケース

- terminalからpending/runningへの復帰、同一キー再送による新Attempt作成は禁止。
- lock期限切れだけを理由にWorkerが直接再取得しない。Recoveryがcall_phaseを判定する。
- marker保存後・実送信前の停止も結果不明として保守的に失敗。自動再呼出しない。
- marker確認は現在の同一実行権が自分の保存応答を失った場合に限る。別実行がstartedを見て呼出してはならない。
- 旧配送の確認・旧Workerのfinishで新generation、新lease、Sessionの新activeを上書きしない。
- 永続化失敗を正常な重複抑止と扱わない。関連item欠落はProvider未呼出の整合性障害。
- DLQから戻したメッセージにも同じowner/世代/処理権/終端確認を適用する。
- Frontendの120秒停止はキャンセル・Backend deadlineではない。

## P2-201との対応とP2-203への引き渡し

| Access Pattern | 必要な識別・検索要件 |
|---|---|
| 公開3 GET | owner＋sessionId/attemptId/evaluationIdで本人取得 |
| 全POST再現 | owner＋Idempotency-Keyで現在業務状態より先に照合 |
| claim/start/finish | owner＋evaluationId、参照先Attempt/Session/Dispatch、leaseVersion/token |
| Dispatch送信 | PENDINGかつ予定到来、送信lease期限を確認 |
| QUEUED起動漏れ（追加） | QUEUEDかつclaim確認期限到来 |
| stale Worker | runningかつlease期限到来、call_phaseで分類 |
| deadline回収（追加） | 全非終端でdeadline到来。配送予定が後でも検出できること |

具体的なPK/SK/GSI・projection・継続位置は[物理設計](dynamodb-design.md)で確定した。
履歴・Profile・Favoriteの新実装は追加しない。原子性の条件はTransaction仕様に統一する。
期限数値・再試行・回復順序は[非同期ADR](../ADR-004-durable-evaluation.md)で確定した。
確認は机上設計レビューであり分散実装の検証ではない。P3で同じR番号を障害注入試験へ移す。

決定理由: 公開状態を増やさず内部実行権を分離する。terminal再開・期限切れWorker直接再取得案を見送った。
関連整合→terminal→deadline→配送/leaseの順で判定する。参照破損は自動修復せず監視・手動対応とし、正常重複と区別する。
PENDINGの送信試行でgenerationは増やさず、送信回数だけ増える。Recoveryの再投入だけ世代を増やす。
配送確認/失敗にも送信lease未期限切れを要求し、期限切れ送信者は更新しない。
時刻を跨いだ送信中の処理とCASの線形化順序はTransaction仕様に従う。
