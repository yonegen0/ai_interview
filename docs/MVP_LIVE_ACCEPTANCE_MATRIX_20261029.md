# MVP公開受入マトリクス（2026-11-03更新）

## 状態と再利用する証拠

**C/D一括承認待ち / RELEASE_HOLD。Phase 5 CはNOT_RUN、B/Dは保存証跡での過去PASS、PR #43はDraft/HOLD。**
本書は準備手順であり、AWS読取り、資格取得、Plan/Apply、OTP、有料AI、招待、公開を承認しない。
Sourceと確認時のremote mainは `b9cf9733efda1a78129e1b1e8f21f10aa0977e9d`。実AWSの現在状態は今回未照会。

| 対象 | 同SHAで再利用する検証 | 限界 |
| --- | --- | --- |
| Frontend | [CI](https://github.com/yonegen0/ai_interview/actions/runs/41315403336)：701テスト、Mock E2E 38、lint/型、production export検査、Storybook、Mock build成功 | 実Cognito/API/CloudFrontの成功ではない |
| Backend | [CI](https://github.com/yonegen0/ai_interview/actions/runs/41315403334)：3,702 PASS / 2 skipped / 57 deselected、契約102、Ed25519 9、Ruff成功 | 実AWS除外試験は未実施 |
| Infrastructure | [CI](https://github.com/yonegen0/ai_interview/actions/runs/41315403377)：オフラインvalidate/Mockとpackage確認成功 | 実State/実効IAM/閉鎖の証明ではない |
| C/D準備 | private revision003：46試験PASS、2,884 binding、保存C Plan監査 | revision003は履歴として保全。新方針のprospective C/D scopeへ切替 |
| 依存 | [11月2日定期監査](https://github.com/yonegen0/ai_interview/actions/runs/41369378374)：production npm/Python成功、all npmは既知moderate 21件でFAIL | 期限付き例外適用CI成功と無例外audit成功は別 |

認証更新・失効・ログアウト・本人切替、APIエラー、二重送信/unknown mutation非再送、通常/Coaching/STAR、静的exportはFrontendの上記試験とソースを再利用する。
Backendは直接Anthropic固定・fallback禁止、全有料経路共通UTC月20/600予約、競合/重複/結果不明、API認可と入力/時間制約を再利用する。
再利用はsource、lock、fixture、設定、実行条件が一致する範囲のみ。資料変更だけでも実行用source/main/State/Planの整合を自動認定しない。

## 阻害要因の分類

| 分類 | 項目 | 最小の解決条件 |
| --- | --- | --- |
| A：公開前必須 | 切替後の新規利用20/600・旧Worker隔離 | g1全有料経路の共通原子予約、切替baseline、未処理/結果不明の扱い、旧writer停止を確認。旧履歴はUNKNOWNのまま許容 |
| A | 必要操作の権限・閉鎖 | 現Role/default policy/boundary、backend policy、閉鎖操作の限定simulationと過去D実成功を組み合わせる。SCP/RCP/発行元の網羅的証明は要求せず、未証明リスクを新承認に含める |
| A | 実JWT/役割/本人分離・HTTPS/CORS・品質 | 実受入証拠。ADMIN/USER相互拒否からUSER/USER成功を推定しない |
| A | セキュリティ・性能 | Issue #92の互換修正または新期限付き判断。Fake p95=2,003.466msはFAIL、実Claude性能NOT_RUN |
| A | 公開後停止・監視・招待 | 隔離/閉鎖手順、担当、通知/heartbeat/queue/Alarm、公開Plan、対象/人数/送付文と別承認 |
| B：公開後 | 過去履歴の復元 | 履歴を変更せずUNKNOWNを保持。完全復元や12月への月替わりを公開条件にしない |
| B：証拠再利用 | 閉鎖権限／重複受入の削減 | 現policy＋限定simulation＋過去D＋同一資格の組合せ、同条件C証拠のPhase 6再利用。Mockで置換しない |
| C：今回から除外 | 独自ドメイン、見た目追加、将来拡張、根拠のない大規模性能改修 | 公開後。必須性能基準を免除する意味ではない |

## 11月中の招待MVP公開方針

2026-11-03のユーザー指示により、12月1日待ちと11月全期間の旧新通算20/600保証を必須条件から外す。
旧履歴、削除/復元履歴、過去の結果不明はUNKNOWNのまま保存し、PASSや過去消費0へ変更しない。
切替後は独立g1の通常・Coaching・STARを共通UTC月20/600の原子予約で制限する。既存g1利用分も残枠から控除し、counter resetや旧データ移行をしない。
旧4関数concurrency0、旧5Role隔離、旧入口停止・native保全と新g1の閉鎖/未処理を実行直前に限定確認する。
過去と切替後の11月合計が20/600を超え得る残余リスク、現在policy確認でも将来閉鎖を保証しないリスクを実AWS有効化前の一括承認に含める。
SCP/RCP/発行元Session Policyの未証明をPASSとせず、過去D実成功＋現在の必要操作確認で実用上の閉鎖可能性を判定する。

## Phase 5 C/DとPhase 6の手順

新C/D scopeも**既存ADMIN 1名＋USER 1名、OTP各1通、固定6有料ケース**。別USER追加は含まない。
private証跡/hashは既存bundleに保持し、JWT/OTP/回答/State/Plan内容/利用者識別子を公開PRへ転記しない。

| 順序 | 実施・判定 | 再利用と停止条件 |
| --- | --- | --- |
| 0. 開ける前 | 切替後20・600残枠/新g1未処理・unknown/旧writer隔離/限定権限/security/source・main・State・Plan・入力hash/新承認を照合 | 新scopeの一括承認後に確認。重大条件不成立ならenable前停止 |
| 1. Preflight | 同一資格1回、実残90分以上、refresh0。必要操作11 SDKの権限確認と切替baseline | AccessDenied/部分一覧/上限超過/未知条件で停止。過去Dを現在PASSへ変換しない |
| 2. Enable | 保存C Plan候補 `f2e29a931ab269bb0815b08c73defe300d52111dc813aa3cf87093a90e68c614`、入口5更新＋Alarm21追加 | source/main/State/入力変化なら流用せず新Planの準備・承認。正常enableと独立整合を確認 |
| 3. C認証 | 各OTP1通、実JWT issuer/client_id/token_use/sub/期限、refresh、signout、役割拒否と相互owner拒否 | masked local console、unknown POST再送0。失敗時に別keyでやり直さない |
| 4. C有料6ケース | 通常ADMIN/USER、Coaching ADMIN/USER、STAR ADMIN/USER。直接Anthropic claude-haiku-5-5 / API 2026-10-21、同時1、65秒間隔 | 固定合成入力、retry/fallback/Provider切替0。HTTP/Schema/Coaching30点・深掘り/STAR3案・根拠・入力保持を確認。品質未判定は残す |
| 5. C会計・運用 | baseline差分ADMIN+3/USER+3/global+6、旧table不変（旧履歴はUNKNOWN）、usage/unknown、queue/heartbeat/Alarm、HTTPS/CORS | 絶対3/3/6や旧消費0を仮定しない。有料600送信やledger巻戻しで境界確認しない |
| 6. D | 一貫したenabled StateからPlan1回、同じ入口5逆更新＋Alarm21削除、Apply1回。実AWSとState/lock/CloudFront Deployedを独立読戻し | D Plan SHAは実生成時に保全し旧SHA流用0。正常enable/整合があればC失敗でも承認内Dを優先。partial/lock/未知drift/不整合では再Applyを強行しない |
| 7. Phase 6残差 | Cの同条件実証拠を再利用。実画面のログイン/失効/ログアウト、深いURL、APIエラー、通常/Coaching/STAR編集、二重送信と利用制限を確認 | B/D/Cを理由なく再実行しない。追加OTP/有料送信を伴うブラウザ操作は別scope/承認 |
| 8. 公開前 | USER/USER実分離、品質/性能/securityの判断、通知到達・停止運用、最新closed Stateから公開Plan、招待対象/人数/送付文 | USER/USERは現2名でNOT_RUN。追加USER/OTP/招待/公開は別承認。未確認をPASSにしない |

各ケースはPASS/FAIL/NOT_RUN、source/config/入力hash、HTTPと相関、送信試行数、usage、品質の人手判定、失敗理由をprivate保存。
根拠違反/unknown/上限投影超過/本人分離失敗/Alarm異常で新規有料送信を停止する。
旧Fake p95 **2,003.466ms > 2,000msはFAIL**。実Claude性能と利用者体験を測定した後、基準変更/例外が必要なら正式判断へ分ける。
従来Scenario Cの基準とFAILは履歴として保持。少人数MVPは30人負荷試験を必須とせず、API応答最大5秒・各評価完了120秒以内を新しい公開基準案として一括承認で判断する。
固定6ケースから30人性能PASSを推定しない。30人試験は現scopeに含めず、NOT_RUNとして公開後へ回す。基準案は承認前に勝手に適用しない。
品質は既存[STARの12品質ケース](STAR_V14_LIVE_ADAPTER.md)を参照し、出典違反0と人手判定を保持。6有料ケースの成功だけで全品質ケースPASSへ変換しない。
実画面は前本人のキャッシュ/下書き非表示、401はGETのみ単回refresh・mutation非再送、403非refresh、生成中編集の保持を確認する。
Webは深いURL/404/MIME/cache/headers、HTTPS/許可・拒否CORS、MSW false、公開変数のみ、worker/source map/秘密ファイル非混入を確認する。

## セキュリティ期限と次の承認

Issue #92の例外は**2026-11-15 09:00 JST**失効。古い成功CI/ビルドを12月の有効な判定へ転用しない。
11月2日のnpm公式registry確認では、最新版ESLint 10.14.0はminimatch ^10.2.6、config-array 0.23.5は^10.2.4、typescript-estree 8.72.1は^10.2.2、docgen plugin 0.9.0はglob ^13.0.6。
[minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249)の修正版11.0.1と[glob advisory](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)の14.0.2をこれらの範囲は含まない。
[ESLint公式リリース](https://eslint.org/blog/2026/10/eslint-v10.14.0-released/)も10.2.6採用を記載。確認したconsumerの単純更新では解消できず、lock/依存/監査条件/期限は変更しない。
互換releaseが揃えば限定更新と全検証。未解消なら最新影響評価に基づく新期限・対象・受容者の明示判断が必要。
現状dev tool graphの2 advisory由来21 moderate、production監査成功。例外は修正完了・公開承認・未知advisory受容ではない。

新方針に対応するprivate revision004を一括承認へ提示する。旧revision003のscope/承認/証跡は変更しない。
固定source/main `b9cf973`、保存C Plan、閉鎖State/入力を照合し、SDK追加最大135（累計520→最大735）、資格追加最大1（累計8→最大9）、開始時215のうち閉鎖専用reserve80を維持する。
内訳は安全確認71、必要権限11、会計/C最大53、D reserve80。init0/enable Apply1/D Plan1/D Apply1、有料最大6、OTP最大2、HTTP最大500、AI見積枠$0.05/AWS追加見積枠$0.10。
既知moderateはproductionへの影響を再確認し、現例外の11月15日09:00 JSTまでの限定受容を正式に再判断する。期限延長・未知advisory・production脆弱性は含めない。
予算/Alarm/見積は請求hard capではない。承認後はPreflight→enable→C→条件付きD→独立読戻しを連続実行する。
正常enable/独立整合があればC失敗でもDを実行。partial Apply/State不整合/lock/未知driftなら再Applyを強行せず承認内の診断で停止する。
追加USER受入・初期招待・正式公開は対象/人数/送付文と最新closed Stateの公開Planが確定した時点でまとめる。PR #113は未merge、PR #43 HOLDを維持する。
