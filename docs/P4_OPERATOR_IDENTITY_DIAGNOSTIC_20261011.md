# Operator本人確認の限定診断

正式dev Plan前の本人確認は、実行対象を固定した別の明示承認に従う。
本書や診断コードの存在はSTS、認証更新、Plan、Applyの承認ではない。

## 2026-10-11の停止原因と修正

保存された一時wrapperの `identity_once.py` は `before-call` hookで
`GetCallerIdentity` と `GetRoleCredentials` 以外を `assert` で拒否した。
期限切れSSO tokenの自動更新は `CreateToken` を必要とするため、そのhookで
`AssertionError: UnauthorizedOperation` となる。API名の記録はassertより後なので、
拒否したAPI名は旧ログに残らない。例外message、traceback、Actor、RequestIdも保存されなかった。

全HTTP送信を禁止し、元hookを元のファイル名/行番号で読み込んだ再現では、
`GetCallerIdentity` → `CreateToken`、hookのAssertionError、HTTP送信0という順序を確認した。
旧停止時の詳細trace自体は存在しないため、この再現を旧live応答の取得証拠と扱わない。
Actor Account/Roleの不一致やSTSのAccessDeniedが観測されたと推測しない。

新しい `backend/skills/p4/operator_identity.py` は、追加認証APIを許可せず、
profileとAccount/Region/SSO設定、環境変数競合をローカル照合する。
そのSSO設定からbotocore互換のcache keyを求め、対応するCLI role credential cacheのみ読む。
期限切れ・不足・不一致ならclient生成前に理由付きの例外で停止する。
SSO token cacheの更新、provider fallback、credential_process、Role assume、IMDSへ進まない。

有効なcacheがある場合だけ、認証情報をメモリ内で固定し、承認されたregional STSへ
`GetCallerIdentity` 最大1回を実行する。SDK total_max_attempts=1と送信回数hookで再送を拒否し、
他のAWS operationはbefore-callで拒否する。
呼出し前のjournalはprivateな新規ディレクトリへ排他的かつdurableに保存する。
呼出し結果が不明なら同じ承認を別ディレクトリ・別runへ移して再実行しない。

## Actor検証と診断証跡

[AWS GetCallerIdentity仕様](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)の
Account、Arn、UserId、ResponseMetadata.RequestIdを保存する。
IAM Role ARNのpathをSTS ARNへ付け足さず、承認されたAccountと正確なRole名から
`arn:aws:sts::<account>:assumed-role/<exact-role-name>/<session-name>` を照合する。
Role session名はcallerごとに変わり得る。形式とUserId末尾の一致を検証するが、
Role名・Accountの不一致をsession名の差として通さない。
IAM pathの確認やRole unique IDのAWS読戻しが必要な工程では、別途明示承認されたGetRoleを使う。
今回のSTSだけの診断ではGetRoleを呼ばず、live IAM path/effective権限を未検証とする。

Actorを値検証の前に記録し、成功/不一致/欠損/認証例外/ローカルcredential不備を区別する。
UTC/JST時刻、例外型、条件コード、ファイル/行/関数を保存する。
Actorが未取得なら値をnullとし、期待Actorで埋めない。
ログ対象は許可されたidentity fieldのみで、raw response、HTTP header、credential、
token、access key、secret、任意の例外messageは保存しない。
private ACLを成立させる前に診断内容を書き込まない。

## 正式dev Planへの影響

既存deployment、認証実装、Terraform/IAM、Plan Attempt1拒否、Apply journal/retry契約は変更していない。
診断失敗を解消するために環境変数やSSO設定を変更せず、認証更新が必要なら明示承認へ戻す。
診断成功だけでAWS State/closed/lock/inventory/GitHub GateをPASSと扱わない。
正式Planは新しい固定main・Artifact・code hash・期限・数量・費用に対する一括承認後だけ実行する。
