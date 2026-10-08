# GPT-6 Luna / Coaching V2 — 承認後の限定実機検証

この文書は実行承認ではない。今回はsuite・offline試験・準備CLIまでで、AWS取引/OTP送信/モデル呼出しは0。
最新基準はCOACHING_V2_APPLY_RESULT_20261008.md。serial12/61/closedの記録を再読取りしてから使う。
[P4 runbook](P4_TERRAFORM_RUNBOOK.md)と[条件付き自動Closure](P4_DEV_VALIDATION_APPROVAL_TEMPLATE.md)を維持する。

## 別途承認するもの

1. 固定commitの新ZIP候補の正式upload（新key/version/checksum、旧Artifactを保持）。
2. 新しいfull saved planの全件レビュー・SHA承認。古い実行済みplanは再使用しない。
3. WIFのAWS/OpenAI側設定、狭いWorker permission/boundary差分。Account issuer/subject/audience/TTLを照合。
4. low/mediumの有料Eval件数上限、利用者データ送信範囲。
5. FakeのみのAWS検証かOpenAI検証かを固定した一時Enablement＋同時の条件付きClosure承認。
6. 既存専用test users、run_id、専用データ、Admin共有bankの排他的検証時間、限定cleanup範囲。

## 実行する順序

- read-onlyでSTS/Region/State lineage/serial/VersionId/lock、最新Artifact/version/alias、main/CIを照合。
- 閉鎖のまま新Artifactと必要構成を配備し、全61資源とprovider manifest設定を読戻す。
- 既存usersだけでEMAIL_OTP・refresh・logout・実JWT expiryを既存auth_e2e経路で確認。tokenはメモリのみ。
- USER A/B/ADMINは別の実認証principal。SSO管理者のDDB許可をRuntime IAMの証明にしない。
- 明示Enablement planを1回適用。State正常なら業務suiteへ進む。partial failureならread-only停止。
- `coaching_live.coaching_flow(a,b,run)`は通常Fakeのcompletedまで、owner/session/Attempt/Evaluation分離、
  202冪等再送、reload、履歴、retry_attemptを検証する。passedは実HTTP応答が成立した場合のみ。
- 3回答はworker_ai_environmentに検証専用Fake設定を明示した別の承認済み構成で検証する。
  INTERVIEW_VALIDATION_ONLY=true、INTERVIEW_FAKE_SCENARIO=coaching_three、専用owner hashを固定する。
  非allowlist principalはPREPARATION_FAILED。利用者回答からscenarioを選ばない。
- provider_failure構成ではfailedとretry_evaluationの新Evaluation/replayを確認する。retry後の成功やRecoveryは
  自動PASSにせず、別の決定的なケース/既存Recovery観測で補足する。
- `admin_flow(user,admin,run,writes=False)`でUSER拒否とADMIN読取を先に確認する。
  writes=Trueは全enabled Cognito usersが承認されたtest usersだけであることと排他的windowを確認した場合のみ。
  元bankをメモリで保持し、run専用質問の追加/編集/移動/削除・同キー再送・版競合を検証する。
  元質問の本文/IDを変えず、終了時に元一覧を確認する。第三者変更を発見したらrestoreで上書きせず停止・証跡化。
- 権限確認はこれらの実取引結果とstatic principal simulationを別欄にする。Transaction/条件更新、Worker/Dispatch/
  Recovery、他環境拒否を実行していない場合はnot_run。JWT認可だけでDDB IAM全ケース成功としない。
- Recoveryは既存OP/AS検証とlogs/metricsで、再配送・結果不明・lease/deadline境界を確認する。
  障害注入・DDB直接変更・function設定変更を黙って実行しない。

## Closureと証跡

業務suiteは`run_with_closure(test_callback, approved_closure_callback, run)`へ接続する。
Closure callbackはP4 runbookの全件監査、最新成功入力から4フラグだけfalse、最新ZIP/version/aliasと61baseline保持、
4閉鎖update＋17validationAlarm destroyだけ、create/replace0、Account/Region/lock/State/State外資源検査を実装した
承認済み実行経路を使う。任意shell hookや無監査applyは接続しない。
テストFAIL・OTP未確認・通知未確認でも、Enablement成功とState整合なら同じ作業で閉鎖まで完了する。
partial applyまたはwhitelist逸脱は再applyせずread-only停止する。
API disabled/両mapping Disabled/Scheduler DISABLED/Alarm0/lockなしを読戻すまでCLOSEDを付けない。

Run journalにはcheck/pass-fail-not_runと、専用作成Session/Attempt/Evaluation/request UUIDだけを保存する。
答案・JWT・email・Token・IAM全文は実行ログへ出さない。失敗時もjournalを消さない。
cleanupはこのjournalとDDBの実キーを照合した限定一覧へ絞る。Scan/全USER partition削除/共有bank無差別resetは禁止。
残存データを一覧化し、既存runの重複実行は同一key再送または新run_idで区別する。無条件deleteはsuiteに含めない。

## 今回使える準備コマンド（外部要求0）

backendディレクトリで、未使用の本人限定保存先を指定する。

```powershell
.venv/Scripts/python.exe skills/p4/provider_eval.py --output .p4-artifacts/<fresh>/eval.json
.venv/Scripts/python.exe skills/p4/coaching_live.py --run-id <unique-id> --output .p4-artifacts/<fresh>/live.json
```

準備結果は実機PASSではない。現行devは閉鎖のまま保持する。
