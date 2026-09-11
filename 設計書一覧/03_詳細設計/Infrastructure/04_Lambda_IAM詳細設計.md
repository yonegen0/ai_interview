# Lambda・IAM詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Role分離
practice / evaluation / adminでIAM Roleを分ける。

## 2. practice
対象DynamoDB + Logsを基本とする。

## 3. evaluation
対象DynamoDB + Logs。
WIF利用時は必要最小限のSTS権限。
Secret方式時のみ`secretsmanager:GetSecretValue`。

## 4. admin
対象DynamoDB + Logs + 必要最小限Cognito Admin API。

## 5. Principle
`Resource="*"`を安易に使用しない。

## 6. 非同期処理の権限

上記は3責務の基本権限。受付元・評価実行先・Route担当と必要な起動権限は非同期方式の決定後に確定する。
起動元／起動先を選ぶ前に広いInvoke権限を追加しない。
[Backend着手前の必須事項](../../04_横断仕様/06_決定事項_未確定事項.md)に従う。
