# OpenAI認証・WIF・Secrets詳細設計

> 文書バージョン: 2.0  
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. Production第一候補
AWS Workload Identity Federation。

```text
Evaluation Lambda IAM Role
→ AWS STS
→ OpenAI WIF
→ OpenAI Project Service Account
→ Responses API
```

## 2. Fallback / Dev
Service Account API KeyをSecrets Managerへ格納。
Powertools Parameters Utility等でCache。

## 3. 禁止
- FrontendへKey
- Git commit
- Lambda envへKey本体
- Terraform variable/stateへSecret実値

## 4. OpenAI Project
専用Project / Service Account / Model制限 / 最小Permission / Spend Limit / Rate Limit。
