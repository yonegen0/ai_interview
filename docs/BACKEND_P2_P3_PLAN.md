# Backend P2・P3 継続実装計画

更新日: 2026-09-13。P2-201〜212は設計確定、P3実装完了・Python検証完了・実DB検証待ち。
F01〜F08のレビュー修正・13本の個別確認・番号別証拠は[P3確認記録](P3_VERIFICATION.md)冒頭を参照。
[全体計画](../AI面接練習Webアプリ｜実装計画.md) v1.5の詳細仕様。
ユーザーのP3実装指示を受けて開始。Python中心・実DBはP4の[環境選定](P3_ENVIRONMENT.md)を採用。
実装と最新検証の正本は[P3確認記録](P3_VERIFICATION.md)。[依存追加方針](DEVELOPMENT_DEPENDENCY_POLICY.md)を維持する。

## 1. 現在地と証拠

P0/P1は既存記録上完了。P1はPython3.13・Memory・Fakeによるローカル業務検証。
P1後のPython3.14.4/依存/内部モデル変更は、P2時点では未検証の先行変更だった。
P2では設計・計画文書だけを変更した。実コードと公開契約の照合、机上シナリオ、
サンプルJSON・文書整合検査を [P2確認記録](p2/P2_VERIFICATION.md) に記載する。
P3では既存184件を再実行し、追加試験を含む結果を別記録へ保存した。P1記録は履歴として維持する。

| 工程 | 決定済み成果物 | 完了根拠 |
|---|---|---|
| P2-201 | 全体計画のAccess Patternを維持 | 既存整理＋A01〜A17で物理操作へ展開 |
| P2-202 | [Entity辞書](p2/entity-model.md)、[状態遷移](p2/state-machine.md) | 全属性・参照・操作結果、R01〜R19 |
| P2-203 | [物理設計](p2/dynamodb-design.md)、[9サンプル](p2/sample-items.json) | 単一保存形式、全AP、GSI/走査継続 |
| P2-204 | [Transaction](p2/transactions.md) T01〜T14 | CAS・非更新条件・競合分類 |
| P2-205 | 同文書の202/応答不明仕様 | 5件commitと元応答再現、R03/R04/R17 |
| P2-206〜209 | [ADR-004](ADR-004-durable-evaluation.md) | 方式比較・処理権・回復順・数値・再試行責任 |
| P2-210〜212 | [保持・Failure Matrix・Security](p2/operations-and-security.md) | R01〜R22、監視/権限/後続Gate |
| P3 | 実装完了・実DB検証待ち | Python・Frontend結果と実DB試験準備は[P3確認記録](P3_VERIFICATION.md) |

公開6 API、全POST冪等性、UTF-16 1〜500・空白禁止・本文無加工、score有限整数値、
exampleAnswer省略可/null不可、405 Allow、本人404、GET非更新、Frontend保存versionと手動復旧を維持。
120秒自動確認停止はBackendキャンセル/評価期限ではない。旧保存データの互換変換は追加しない。

## 2. P3開始前Gate

以下の開始Gateはユーザー指示後に実施済み。実DB環境の構築・検証はP4へ引き継ぐ。

1. git status、対象AGENTS、現在の対象内容と差分を再確認する。
2. 先行変更を編集元として棚卸しする。無関係な変更、旧skill削除、ZIPを勝手に復元/削除しない。
3. P3-302の選定票を作る。既存環境と必要試験を確認し、追加依存を最小化する。
4. Docker既存ならLocal/Docker、Java既存ならLocal/Java、両方なければ導入負担とAWS devを比較する。
   その他AWS公式に沿った方法も同じ試験を満たすか評価する。Localは必須でない。
5. 選定理由、Production/開発補助の別、追加依存、費用、認証、合成データ、
   接続先、起動/停止/後片付け、CIの実機試験方法を記録する。
6. 必要な環境変更の理由と影響を事前説明する。AWS案の選定だけでAWS操作をしない。
   P4 AWSへ実機試験を送る場合は「実装」と「永続化・競合検証」の完了を分ける。

Python3.14・uv・Pydantic・pytest・Ruff・AWS SDKは基本方針。今必要な差分だけをProject Localで扱う。
Javaを選んでもBackendアプリ依存ではなくLocal補助Runtime。
Docker/Javaがない→Portable Javaを自動取得、という判断はしない。

## 3. P3実装順序・受け入れ証拠

| タスク | 具体作業 | 受け入れ証拠・依存 |
|---|---|---|
| P3-300 | 先行Python/pyproject/lock/Ruff/CIと.gitignore差分を確認。現環境で必要な同期と検証だけ | Ruff、全既存pytest、CLI。失敗を隠さず原因を分離 |
| P3-301A | 辞書のDispatch/実行設定/LeaseClaim/DeliveryClaim/正常結果とDB例外を実装。時計・Publisher境界 | 型検証と初期値、全有効/無効組合せ |
| P3-301B | Memory受付5件、開始/finish/recover契約を接続。Worker生存実行フラグ | Fake時計R05〜R19/R21。旧内部snapshot依存試験はMemory専用 |
| P3-302 | 上記環境選定を正式記録し、必要な場合のみ構築 | 選定接続先への明示設定。Localモード設定不足で実AWSへfallback禁止 |
| P3-303 | native item/JSON Serializer、PK/SK、rev、GSI Mapper、Cursor | 9サンプル往復、Decimal/任意項目/UTC/surrogate/サイズ上限 |
| P3-304 | 本人3 GET、I強整合照合、内部TransactGet | 全API契約、他owner404、未完了Feedback409、GETでProvider0回 |
| P3-305 | T01〜T03の受付Tx、固定ID/時刻/応答、Session version | R01〜R04、同時Answer/Next、全Txの部分保存なし |
| P3-306 | 応答消失・再送token・予算・状態再読取り | 同時同キー3 POST、異Path/異本文、500受付不明→元応答 |
| P3-307 | T04〜T06、lease/開始/終端fencingとSession保護 | R06/R09〜R14、旧実行権、開始不足予算、started再呼出禁止 |
| P3-308A | due Query/3 partition/Cursor CAS/T14 | 100件超・途中停止・古い候補・期限逆転・回復競合、R16/R18/R22 |
| P3-308B | T07〜T13、Publisher fake、Streams/SQS/Scheduler adapter | 配送障害と先着Worker、再帰送信なし、R05〜R19 |
| P3-309 | 公開業務操作から同一契約suiteをMemory/DBに適用 | 6 API・score・500/501・全POST、原子性/配送suite。実装固有試験と区別 |
| P3-310 | 独立instance/process競合、再起動、CLI、CIと証拠更新 | R20＋各競合。Local選択時だけ永続volume再起動。AWS試験待ちは明示 |

P3-302の選定相談は開始Gateで先に行えるが、Mapper/DB実装より前に確定する。
AWS SDK、PK/SK、条件式をApplicationへ露出させない。Worker/bootstrap/CLIは内部処理権接続のためP3で変更可能。
テストTable削除はそのrunで作成した専用Tableだけ。既存Table/本番/他試験のTableを削除しない。
未実行DBsuiteをskipしてCI成功扱いにせず、選定環境への疎通失敗は失敗、P4送りなら検証待ちを明示する。

## 4. P3完了の判定

[確認記録のP3試験仕様](p2/P2_VERIFICATION.md)を全て追跡可能にする。
Backend Ruff/全pytest/CLI、Frontend共通契約fixtureの成功、独立process・原子性・配送回復・保存応答再現を証拠にする。
Fake/Mockだけで実DynamoDBの競合・永続保存を保証しない。
実装済みでもAWS dev試験をP4へ送った分は「P3実装完了・実機検証待ち」であり、P3全体完了ではない。

P4: FakeのままStreams/SQS redrive/IAM/JWT/Alarmを検証する。Local成功で代用しない。
実個人データ前に保持・本人削除・Backup復元時処理を決定する。
P5: 実Provider/SDK/認証・料金上限・再試行無効を確認する。実呼出は明示依頼後。
P6: Frontend認証・実API・保存分離。P7: Production準備、既知WebP1254px対512pxとE2Eを正しく解決。
除外や期待値変更で既知画像問題を成功扱いにしない。

## 5. P2終了時の未検証先行変更（履歴）

以下はP2終了時点の記録。P3では内部モデルを接続、ignoreを補完し、Python試験を再実行した。
ZIP/cacheは保持。最新の状態は[P3確認記録](P3_VERIFICATION.md)を参照する。

| 対象 | 現在の変更/注意 |
|---|---|
| backend/.python-version | 3.14指定 |
| backend/pyproject.toml・uv.lock | Python>=3.14,<3.15、boto3、Ruff py314、lock同期 |
| .github/workflows/backend.yml | Python3.14へ変更 |
| backend/src/interview_backend/models/internal.py | timestamps、Dispatch/lease/結果型、State.dispatches追加。動作未接続 |
| backend/.gitignore | .local/.uv-cache追加時に従来ignore項目が置換。今回戻さない |
| Backendプロジェクト環境 | Python3.14.4取得・.venv再作成済み。今回再同期/更新しない |
| backend/.local/java.zip・dynamodb.zip | 取得済み、展開/Java配置/Local起動未実施。存在を利用理由にしない |
| cache/既存ユーザー変更 | 保持。権限警告のあるcacheも削除しない |

今回のP2設計完成はこれらの正常動作を保証しない。P1の成果物・検証記録も書き換えて成功実績を作らない。
