# Infrastructure基本設計書

> 文書バージョン: 2.0  
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. AWS
- Cognito
- API Gateway HTTP API
- Lambda
- DynamoDB
- S3
- CloudFront / OAC / CloudFront Functions
- IAM
- CloudWatch
- Route53
- ACM
- Secrets Manager（API Key方式を使う場合）

## 2. Region
Applicationは原則ap-northeast-1。
CloudFront用ACM Certificateはus-east-1 Provider Aliasで管理。

## 3. Terraform
hashicorp/awsを基本とする。
awsccは通常Provider未対応時のみ検討。

## 4. State
専用S3 backend。
versioning / encryption / public access block。
`use_lockfile=true`。
DynamoDB State Lockingは新規採用しない。

## 5. Build責務
Frontend build、Lambda dependency/package、test、Question Bank seed、Secret実値投入はTerraform外。
