---
document_id: DD-INF-001
title: "Infrastructure詳細設計 INF01 CDK・スタック・環境設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. IaC

AWS CDK v2 / TypeScript。

Repository例:

```text
infra/
  bin/app.ts
  lib/
    auth-stack.ts
    data-stack.ts
    api-stack.ts
    web-stack.ts
    monitoring-stack.ts
  config/
    dev.ts
    prod.ts
```

# 2. Stack

## AuthStack
- Cognito User Pool
- App Client
- Groups
- SES/Cognito email設定

## DataStack
- DynamoDB

## ApiStack
- Lambda
- IAM
- HTTP API
- JWT Authorizer
- Lambda Auth Guard用`EXPECTED_APP_CLIENT_ID` / Table情報を環境変数へ注入

## WebStack
- S3
- CloudFront
- OAC
- CloudFront Function
- Response headers

## MonitoringStack
- Log retention
- Alarms
- Budgets関連

# 3. Environment

Resource prefix:
```text
interview-training-dev-
interview-training-prod-
```

dev/prodは物理Resourceを分離する。

# 4. Config

Config file:
- region
- domain
- dailyLimit
- lambdaConcurrency
- logRetention
- budgetThreshold
- bedrockInferenceTarget
- questionBankVersion
- promptVersion
- indexedDbRetentionDays（Frontend build config。初期30）
- indexedDbMaxEntries（Frontend build config。初期50）

Secretはconfig fileへ平文保存しない。

# 5. Region

Primary:
`ap-northeast-1`

Bedrock JP GeoのDestination Region制約とOrganization SCPを確認する。

# 6. Outputs

Frontend buildで必要:
- API Base URL
- Cognito User Pool ID
- Cognito App Client ID
- Region

CDK OutputからCI/CD environmentへ渡す。

# 7. Cross Stack

Stack間参照を増やしすぎない。
必要:
- UserPool → Api
- Table → Api
- API URL → deployment output

# 8. Removal Policy

dev:
- destroy容易

prod:
- DynamoDB RETAINを検討
- Cognito RETAINを基本
- S3静的Bucketは再生成可能だが誤削除防止を検討

# 9. Tags

- Project=AIInterviewTraining
- Environment=dev/prod
- ManagedBy=CDK

# 10. Deploy Order

1. Auth
2. Data
3. Api
4. Web
5. Monitoring

CDK dependencyで自動解決できるものは明示順序に依存しすぎない。
