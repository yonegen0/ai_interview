---
document_id: DD-INF-006
title: "Infrastructure詳細設計 INF06 監視・コスト・セキュリティ・運用設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 監視方針

「障害を全部予防する」より、
利用者が少ないMVPで異常を早く把握し、費用暴走を防ぐことを重視する。

# 2. CloudWatch Metrics

## API Gateway
- Count
- 4xx
- 5xx
- Latency

## Lambda
- Invocations
- Errors
- Duration
- Throttles
- ConcurrentExecutions

## DynamoDB
- ThrottledRequests
- On-demand usage
- Maximum throughput関連metric

## Bedrock
- invocation
- latency
- error
- token usage（提供Metric/response範囲）

# 3. Alarms

最低限:
- API 5xx上昇
- feedback Lambda error
- feedback Lambda throttle
- DynamoDB throttle
- AI invalid response増加
- DailyLimit異常増加
- Budget閾値

# 4. Logs

Log retention:
- dev短め
- prodは業務/セキュリティ要件で決定

ログ本文にPIIを含めないため、
長期保存リスクを抑える。

# 5. Cost Defense

```text
Authentication / PROFILE status gate
↓
Daily per-user AI limit          <- 主要アプリ制御
↓
Idempotency + same practiceId retry
↓
API Gateway route throttling    <- burst抑制 / best-effort
↓
Lambda reserved concurrency     <- feedback同時実行上限
↓
DynamoDB maximum throughput     <- 補助 / best-effort
↓
AWS Budget / Alarm              <- 遅延のある監視・通知
```

位置付け:
- Daily AI Limit: Bedrock呼び出し直前の利用量制御
- API Gateway throttling: best-effort targetで、保証されたrequest ceilingではない
- Lambda Reserved Concurrency: Functionが指定同時実行数を超えてscaleしないよう制限する。ただし月額費用のHard Capではない
- DynamoDB Maximum Throughput: best-effort target。burstで一時超過し得る
- AWS Budgets: billing data更新に遅延があるためリアルタイム停止装置にしない

単一機能をHard Cost Capとみなさない。

# 6. Security Checklist

- [ ] S3 Public Access Block
- [ ] OAC
- [ ] HTTPS
- [ ] Security Headers
- [ ] Static Hosting前提のCSPをReport-Onlyで検証後enforce
- [ ] production `unsafe-eval`なし
- [ ] third-party script原則なし
- [ ] CORS prod origin限定
- [ ] App Client secretなし
- [ ] PreventUserExistenceErrors
- [ ] JWT Authorizer
- [ ] Lambda `token_use=access` validation
- [ ] Lambda `client_id` validation
- [ ] Lambda group auth
- [ ] `PROFILE.status=ACTIVE` gate
- [ ] Disable時 `AdminUserGlobalSignOut`
- [ ] Frontend Token Storage = `sessionStorage`
- [ ] IAM least privilege
- [ ] PII log禁止
- [ ] Token/OTP log禁止
- [ ] AI input length
- [ ] Nova `stopReason=tool_use` validation
- [ ] Schema validation
- [ ] REQUEST + USAGE transaction
- [ ] Daily limit
- [ ] IndexedDB sub isolation / 30日expiry / logout cleanup

# 7. Operational Runbook

## AI障害
1. Bedrock error/latency確認
2. Lambda error確認
3. Region/model availability確認
4. 必要に応じてAI機能停止/limit縮小

## OTP障害
1. SES status/quota
2. Cognito auth error
3. verified identity
4. bounce/complaint

## Cost spike
1. Budget alert
2. feedback invocation
3. user usage
4. reserved concurrency/limit縮小
5. 必要ならAI route一時停止

# 8. Backup

- DynamoDB PITR
- Git: CDK / Prompt / Question Bank
- S3 static: build artifact再生成
- CloudFormation/CDKでinfra再構築

# 9. Data Retention

Server-side retention:
- DynamoDB本体データ保存期間はTBD
- CloudWatch retentionはdev/prodで明示設定
- Cognito user deletion方針は運用確定時に揃える

Client cache:
- IndexedDBは直近50件目安
- 全個人履歴cacheは最終アクセスから30日で期限切れ
- logout時current sub削除
- login/startup時owner sub不一致削除
- `ACCOUNT_DISABLED`時削除
- 手動「この端末の履歴データを削除」を提供

ServerとClientの削除方針は、DynamoDB retention確定時にプライバシーポリシー/運用手順と一貫させる。

# 10. Incident Privacy

障害調査のためにanswer本文を常時ログ化しない。
必要な場合も明示的な一時診断フローと権限/保存期限を設計してから行う。

# 11. Release

Release前:
- lint/typecheck/test
- CDK diff
- dev deploy
- smoke
- prod deploy
- CloudFront invalidation
- smoke
- alarms確認

# 12. Rollback

Frontend:
- 前build artifactへ戻す

Lambda:
- version/previous artifactへ戻す運用を用意

Prompt/Question:
- versionを戻せる

DynamoDB schema:
- additive changeを基本とし、破壊的migrationを避ける

---

## 参照公式ドキュメント

- [DynamoDB - Maximum throughput for on-demand tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html)
- [AWS Lambda - Reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [API Gateway - HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [AWS Budgets - Best practices](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)
- [AWS WAF - Supported resources](https://docs.aws.amazon.com/waf/)
- [CloudFront - Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

