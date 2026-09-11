# Cognito詳細設計

> 文書バージョン: 2.0  
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. User Pool
Passwordless Email OTP。

## 2. App Client
SPA向け。Client Secretなし。
`ALLOW_USER_AUTH`利用を前提とし、実装時の最新Provider schemaを確認する。

## 3. User Registration
Self sign-up OFF。
管理者のみUser作成。

## 4. Group
USER / ADMIN。

## 5. Token
APIにはAccess Tokenを使用。
