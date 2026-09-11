# Idempotency詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 対象とキー

全POST（Session作成・回答送信・次問操作）でFrontend生成UUIDのIdempotency-Keyを必須とする。
実BackendはJWT sub本人のスコープでキーを識別する。
sessionId／attemptId／evaluationIdはBackend生成のリソースIDであり、冪等キーと分離する。
evaluationIdだけではSession作成と次問操作の冪等性を担えない。

## 2. 初回・再送

- ユーザーとキーを原子的に予約し、Method・Path・検証済みPayloadの識別情報を記録する。
- 同一要求は保存済みHTTP StatusとResponseを返す。Method・Path・Payloadの不一致は409。
- 回答受付の要求とAttempt／Evaluationの関連を永続化し、202応答を再返却できるようにする。
- 応答消失後も同じキーとPayloadを使用し、Attempt・AI処理・集計を重複作成しない。
- 確定失敗後の再挑戦は新しいキーとAttempt。同じキーの再送を新しい評価開始に扱わない。
- 処理中の別キー回答、古い結果からの次問操作はSession状態の409で拒否する。

## 3. 要求記録とEvaluation

要求記録は所有者、キー、Method、Path、requestHash、内部処理状態、保存済みHTTP Status／Responseを持つ。
lockExpiresAtは次工程で定義する候補。内部要求状態と公開Evaluationのprocessing／completed／failedを同一視しない。
評価が完了しても受付応答を再返却し、最新状態は評価GETから取得する。

## 4. 実装前に確定すること

保存途中の同時再送、予約後の停止、起動漏れ、重複実行、ロック期限切れ、外部AIの完了不明を扱う。
物理キー・Transaction・保持期間・再実行条件は[必須事項](../../04_横断仕様/06_決定事項_未確定事項.md)で確定する。
MSWのタブ内Repositoryは本番排他制御の実装ではない。
目的は二重課金・二重保存防止だが、外部AIの応答消失まで含む保証は回復設計なしに断定しない。
