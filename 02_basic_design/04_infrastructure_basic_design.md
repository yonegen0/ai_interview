---
document_id: BD-INF-001
title: "AI面接練習Webアプリ MVP 基本設計書（インフラ）"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. IaC

AWS CDK v2 / TypeScriptを使用する。

推奨Stack:
- AuthStack
- DataStack
- ApiStack
- WebStack
- MonitoringStack

環境:
- dev
- prod

# 2. Web配信

```text
CloudFront
  ↓ OAC
Private S3
```

- S3 Website Endpointは使わない
- Public Access Block有効
- OACを使用
- HTTPSのみ
- CloudFront Functionで`/route/` → `/route/index.html`解決
- Security HeadersはCloudFront側
- Static Export + MUIではrequest nonceを生成できないため、nonce CSPは採用しない
- production CSPは`unsafe-eval`を許可しない
- Static構成上必要な`unsafe-inline`は最小限に限定し、third-party scriptを原則禁止する
- `connect-src`はWeb origin、HTTP API、Cognito endpoint等の必要先だけallowlistする

# 3. Cognito

- User Pool
- Essentials以上
- Email OTP
- Self sign-up off
- `ALLOW_USER_AUTH`
- `GenerateSecret=false`
- `PreventUserExistenceErrors=ENABLED`
- USER/ADMIN Groups
- MFA requiredは使わない

# 4. API

API Gateway HTTP API:
- JWT Authorizer
- Lambda proxy integration
- CORS
- route throttling

JWT Authorizerはissuer/audience等を検証するが、Access TokenとID Tokenの区別をLambdaだけに委ねない前提にはできない。
Lambda共通Auth Guardで`token_use=access` / `client_id` / Group / `PROFILE.status`を追加検証する。

HTTP APIを採用するため、API Gateway REST API固有のAWS WAF直接統合は前提にしない。

# 5. Lambda

- Python
- arm64を第一候補
- function単位IAM
- Reserved Concurrencyはfeedback Lambdaで検討
- Provisioned Concurrencyは初期導入しない

# 6. DynamoDB

- On-Demand
- PITRをprodで有効化推奨
- Encryption at rest
- Maximum Throughputはコスト防御の補助
- GSI最小限

# 7. Bedrock

- Amazon Nova 2 Lite
- JP Geo Cross-Region Inference
- model/inference targetは環境変数
- feedback LambdaだけInvoke権限

# 8. SES

Cognito Email OTPのメール送信にSESを設定する。
本番前にProduction access、送信元Identity、Regionを確認する。

# 9. 監視・コスト

- CloudWatch Logs/Metrics
- API 4xx/5xx/latency
- Lambda errors/throttles/duration
- DynamoDB throttle
- Bedrock invocation/latency
- AWS Budgets
- Alarm

役割:
- Daily AI Limit: アプリ上の主要コスト制御
- API Gateway throttling: burst/過負荷抑制。best-effort targetでHard Ceilingではない
- Lambda Reserved Concurrency: feedback同時実行の上限・runaway抑止
- DynamoDB Maximum Throughput: 補助的な利用量/コスト抑制。best-effort target
- AWS Budgets: 遅延のある監視/通知。リアルタイム停止装置にしない

# 10. WAF方針

MVP:
- HTTP API直接
- Cognito
- API throttling
- Daily AI Limit
- Lambda Reserved Concurrency
- Budget

APIにWAFが必須となる場合は、
CloudFront API origin方式またはREST API移行をADRで比較する。

# 11. Backup/Recovery

- CDKから再構築可能
- DynamoDB PITR（prod）
- Question Bank/PromptはGit管理
- S3 static assetは再build可能
- Cognito User Pool復旧は別途運用考慮

# 12. Secrets

FrontendにSecretを置かない。
`NEXT_PUBLIC_*`は公開値のみ。
AWS credentialをFrontendへ配布しない。

---

## 参照公式ドキュメント

- [CloudFront - Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [CloudFront - Default root object](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DefaultRootObject.html)
- [API Gateway - Choose between REST APIs and HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
- [API Gateway - AWS WAF for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html)
- [DynamoDB - Maximum throughput for on-demand tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html)
- [AWS Lambda - Reserved and provisioned concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [Amazon Cognito - UserPoolClientType](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_UserPoolClientType.html)
- [Amazon Bedrock - Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [API Gateway - HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [AWS Budgets - Best practices](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)
- [MUI - Content Security Policy](https://mui.com/material-ui/guides/content-security-policy/)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

