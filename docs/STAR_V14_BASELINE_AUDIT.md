# STAR Ver.1.4 基準監査

基準: 2026-10-10、GitHub main / ローカル HEAD `bc0919e13477f4d86609e1c7ed51590e118a8fd2`。実装開始時にGitHub connectorでmainを読み戻し、一致を確認した。
作業branch: `codex/star-assist-v14-offline-20261010`。独立worktree: `.p4-artifacts/star-assist-v14-offline-20261010/source`。

ユーザーの最終レビュー反映計画が添付2資料の未確定事項に優先する。通常下書きと業界・企業名の14日保持は承認済み仕様。添付のP4 Bootstrap引継ぎとAGENTS.mdは既存証跡の保護・将来の配備運用に適用し、今回のオフライン作業にAWS操作の権限を付与しない。

## 既存契約

|領域|監査した実装|維持する契約|
|---|---|---|
|API|`api/handler.py`, `application/service.py`, `models/public.py`|既存回答Body・fingerprint・202応答・同キー再送|
|V2|`repositories/coaching.py`, `evaluation/provider.py`, Frontend coaching schemas|30点、400コードポイント、文字数減点、最大3深掘り、累積正式履歴、4操作|
|V1|public models,旧保存codec,旧pending|100点、500 UTF-16、旧Body・旧保存データ|
|DB|`repositories/{domain,memory,dynamodb,codec}.py`|CAS revision・canonical JSON・350 KiB制限・strong read・時刻CommitWindow|
|配送|`evaluation/{events,dispatch,worker}.py`|DispatchだけがStreams対象、SQS strict契約、lease、deadline、重複配送|
|復旧|`useAnswerOperation.ts`, `storage/recovery.ts`, MSW store|固定key/元Body、本人scope、401再送、pending優先|
|Terraform|service runtime/IAM/auth/data、provider locks|既存4フラグ、Streams filter、MaximumConcurrency=2、provider選択|

既存事前Backend166 PASS / Frontend140 PASSはユーザー計画の基準情報。今回の実装後実測とは混同しない。

## 保全

元Windows作業ツリーをreset・stash・cleanしていない。private証跡、正式Artifact、saved Plan、journal、Draft PR #5を編集していない。既存変更と証跡indexのSHA/サイズを専用private台帳で記録し、終了時に照合する。依存追加・lock変更・main merge・pushを行わない。

オフラインBackend試験にはsocket/SDK送信を拒否するautouse fixtureがある。検証子プロセスからAWS/TF/OpenAI環境変数を除外し、DynamoDBはMemory/SDK Stubberのみ、AIは専用Fakeのみ。Terraformは公式ZIPと既存lock checksumを照合したfilesystem mirrorだけを使用し、隔離コピーでbackend=false validate/mockを実行する。
