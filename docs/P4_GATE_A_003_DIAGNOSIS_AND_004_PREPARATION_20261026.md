# Gate A 003解析と004準備（2026-10-26）

## 結論

003はSTOPPED・承認消費済み。失敗段階は2回目のPlan用OIDCトークン取得中の
`HTTPError`と確定した。HTTP番号・拒否本文・Request IDは保存されておらず、
上流側の根本原因は復元不能。権限不足・期限切れ・rate limit・一時障害のいずれとも断定しない。
診断欠落は修正したが、実OIDC障害の解消は未確認。004は準備草案であり、正式承認・dispatch不可。

## 証跡と到達状況

- [003 Run 40317045177](https://github.com/yonegen0/ai_interview/actions/runs/40317045177)、Attempt 1。
- source: `ffe3634d477cc7f536bb14ee5224ed85220abafd`。
- 本人がローカル復号したZIPのhashと検証記録、元CMSのhashを再照合。
  連番29件、Run/Attempt/承認hashと対象sourceの関連実装を照合した。平文journalは公開しない。

| 工程 | 確認結果・限界 |
| --- | --- |
| Plan用OIDC | 1回目完了、2回目開始後にHTTPError。2回目完了なし |
| STS | AssumeRoleWithWebIdentity 1回完了、GetCallerIdentity 1回完了 |
| 初回事前State確認 | 呼出しが正常復帰。lock不在確認、VersionId固定Getと再HEAD、閉鎖設定検査を通過 |
| State identity | lineage/serial/VersionId自体はjournal未保存。過去値を今回の観測値として転記しない |
| Lambda ZIP | buildが戻り、承認digest照合を通過。S3 uploadには未到達 |
| 2回目のState確認 | 認証中に停止。State読取り本体には未到達 |
| Terraform init / plan / apply | すべて0。対応process開始記録なし、実装上も未到達 |
| lock取得・State書込み | このRunでは未到達。停止後の実State/lockは未観測 |
| artifact用認証 / S3 Put | すべて未到達 |
| saved Plan / Plan S3 VersionId | 生成工程未到達。生成なし |

初回State確認の成功は、後続のZIPビルドとdigest比較、2回目のOIDC開始が観測され、
固定sourceの`ci_deploy.main`がこの順に直列実行することから確定できる。
Stateは前後比較完了ではなく、現在のlock不在・State不変を保証しない。

AWS APIは少なくとも6要求（STS 2、S3 State/lock読取り4）。lock HEADが403の場合の
ListObjectsV2やページングはjournalに記録されないため、正確な要求数・個々のHTTP応答は不明。
S3 PUT/DELETE、Terraformのlock書込み・Applyには未到達であり、AWS未接続とは報告しない。
`operation=build`の6 processはgitコマンドも含み、ZIPを6回ビルドした意味ではない。

## 最小修正

`ci_identity.request_token`のHTTPError処理だけを追加した。既存の暗号化journalへ
`oidc-http-error`、role、整数HTTP番号、厳密な書式に一致する相関IDだけを保存する。
HTTP本文・URL/query・例外本文・全headers・JWT・Authorizationは読取り/記録しない。
public artifactは従来どおり固定summaryとCMSのみ。

OIDC/STS回数、deadline、Role/subject/claim検証、権限、redirect拒否、再試行禁止、
State検査、init/Plan/Apply経路、依存/lock、Terraform/AWS Provider版は変更していない。
トークンの再利用・キャッシュ・fallbackは追加していない。HTTP失敗の原因を推測して
認証方式やIAMを変える修正ではない。

## オフライン検証

- Python 3.14.9 / uv 0.13.5、既存lock、`--offline --locked`で実行。
- 重点回帰162件PASS。2回目OIDCの302/401/403/404/422/429/500/503で、診断保存後の
  fail-closed、後続STS/追加OIDCの抑止、元例外分類の保持、Secret非出力を確認。
- 不正HTTP番号・未知/長大IDの除外、本文非読取り、CMS実ローカルroundtrip/改変拒否を確認。
  暗号化試験はdisposable鍵のみ。本人の秘密鍵・パスフレーズは使用していない。
- Backend Ruff check PASS、変更Python3ファイルのformat check PASS、diff check PASS。
- 最初の試験は既存OpenSSLがPATHにないため153 PASS / 9 setup ERROR。
  子プロセスのPATHに既存Git同梱OpenSSLを追加して、同じ162件を全件再実行しPASS。
  依存追加・テストskip・期待値緩和なし。
- これはオフライン結果。真正CI・実AWS/OIDC成功・実Plan成功を意味しない。

## 004の準備と正式固定条件

Git管理外の新しい`release-gate-a-20261026-004`に候補入力hash、承認草案、手順を保存する。
準備状態は`DRAFT_NOT_APPROVABLE_NOT_EXECUTABLE`。旧002/003の承認・期限・入力は不変。
草案に承認の発行/期限は付けず、正式package・dispatch入力・本人承認記録を生成しない。

正式な004を準備完了にするには次を満たす必要がある。

1. 上流HTTP原因の不明を解消するか、不明を明記した新しい限定診断実行の範囲を別途定義する。
   ローカル修正だけを実障害解消として扱わない。
2. 診断修正を保護されたPR/CI経路でmainへ反映し、clean mainの最終SHAを固定する。
   現在はローカル修正のみ。mainは旧SHAのまま。mainへの直接push/保護迂回はしない。
3. ZIPのsource/lock/全entry整合、構成hash、recipient、package baseline、期限・回数・費用、
   controller自身とpreflight参照コードのhashを最終SHAに対して再固定する。
   旧controllerの旧Secret更新日時やsource manifestをそのまま再利用しない。
4. その時点の72時間windowで新しい全文hashを発行し、本人が004だけを明示承認する。
   003の承認・過去read-only承認は再利用しない。承認前のSecret更新/readiness変更/dispatchなし。
5. 承認後も直前main/必須CI/保護/既存Run履歴/Secretメタデータ/readinessを照合する。
   実State読取り・lock検査も新承認の対象。未知/失敗時の再実行・force-unlockは禁止。

将来のGate Aはartifact登録や通常lock操作を含み得るため、現在のAWS書込み禁止から
暗黙に許可されたとは扱わない。新承認に対象操作・上限を明記する。
Gate Bは実saved Plan/hash/全差分に対する別承認であり、004草案からApply権限は発生しない。

## 今回の副作用と保全

今回の追加AWS要求、Terraform init/plan/apply、GitHub書込み、dispatchはすべて0。
2026-10-26 21:09:12 JSTのGitHub GETでmainは旧SHA、dev-plan/dev-applyのreadiness全4項目false、
Issue #50 OPEN、PR #43 OPEN/Draftを確認。HOLD解除操作なし。
旧002/003の固定資料・実行証跡と復号済みjournalは別manifestでhashを保全・再照合する。

## 公式資料との照合

[GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)の
URL/リクエスト用tokenによるJWT取得と既存実装を照合した。003はJWT取得側で停止しており、
2回目のSTS拒否やTerraform failureとは区別する。
[Python 3.14 urllib.error](https://docs.python.org/3.14/library/urllib.error.html)の
HTTPError.code/headersだけを限定利用する。これらの仕様から003の未保存HTTP番号は推定しない。
