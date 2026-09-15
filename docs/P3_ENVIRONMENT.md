# P3検証環境の選定

2026-09-12、ユーザー選択: Python中心、実DynamoDB試験はP4。

P3はPython 3.14 / uv / Pydantic / pytest / Ruff / boto3を使用する。
Memory、Fake時計・Provider・Publisher、botocore Stubberで契約とSDK境界を検査する。
Java、Docker、Motoは追加しない。取得済みZIPは保持し、展開しない。
既存のPython・lock・CI・内部モデル差分は編集元として保持する。

通常CLI/CIはMemoryとFakeを使う。実AWS利用はmode=aws、region、tableを明示する。
接続先不足でAWSへ暗黙fallbackしない。RepositoryはTableを作成・削除しない。
資格情報はAWS SDK標準経路を使い、ソースやログに保存しない。

P4は合成sub・合成回答を使い、run専用Tableで実Transaction、独立process競合、
アプリ再起動後の永続化、GSIページングを確認する。費用とAWS認証・権限の準備はP4。
試験専用Tableの作成・後片付けは明示実行するfixtureに限定する。
P3の到達表記は「実装完了・実DB検証待ち」。実装・試験結果は[P3確認記録](P3_VERIFICATION.md)。
