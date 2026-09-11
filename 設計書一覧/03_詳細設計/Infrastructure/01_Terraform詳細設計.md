# Terraform詳細設計

> 文書バージョン: 2.0  
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Directory
```text
infrastructure/terraform/
├─ bootstrap/
├─ environments/dev/
├─ environments/prod/
└─ modules/
   ├─ auth/
   ├─ api/
   ├─ compute/
   ├─ database/
   ├─ frontend/
   ├─ security/
   └─ observability/
```

## 2. State
S3 Backend、`use_lockfile=true`。
State Bucketはbootstrapで先に作成。
Application Bucketと分離。

## 3. Provider
hashicorp/awsを基本。
CloudFront ACM用にus-east-1 Alias。
awsccは必要時のみ。

## 4. Terraform外
Build/Test/Package/Secret実値/Question seed/Application code。
