---
document_id: DD-INF-005
title: "Infrastructure詳細設計 INF05 DynamoDB・Bedrock設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. DynamoDB

Mode:
On-Demand

Primary:
PK/SK string

GSI:
- GSI1 Admin user
- GSI2 Favorite

# 2. Protection

prod:
- PITR ON推奨
- Encryption at rest
- Deletion protection/Removal Policy検討
- IAM least privilege

# 3. Maximum Throughput

On-Demand Maximum Throughputをコスト暴走防止の補助として設定可能。

注意:
AWS公式上best-effort targetであり、絶対的なHard Ceilingとは扱わない。

# 4. Capacity

本MVPは小規模のため初期Provisioned Capacity最適化を行わない。
実利用Metricを見てOn-Demand継続可否を判断する。

# 5. Bedrock

Runtime:
Amazon Bedrock Runtime

Model:
Amazon Nova 2 Lite

Inference target:
JP Geo Cross-Region

# 6. Region Policy

Geo inferenceは複数Destination Regionを使う可能性がある。
Organization SCPやRegion deny policyと競合しないことをdeploy前に確認する。

# 7. IAM

feedback LambdaだけBedrock権限。

可能な範囲で利用Model/Inference ProfileにResourceを限定。
AWSの実際のIAM Action/ARN仕様は実装時に公式確認。

# 8. Invocation Logging

Model Invocation Loggingはデフォルト無効方針。

有効化する場合:
- Prompt/responseにPII
- 保存先
- retention
- access
を承認してから。

# 9. Model ID

Environment:
```text
BEDROCK_BASE_MODEL_ID=amazon.nova-2-lite-v1:0
BEDROCK_INFERENCE_TARGET_ID=jp.amazon.nova-2-lite-v1:0
```

コードへ埋め込まない。

# 10. Prompt Version

```text
PROMPT_VERSION=feedback-v1
QUESTION_BANK_VERSION=questions-v1
```

履歴へ保存。

# 11. Cost

主要AIコストはtoken usage/呼出量。
以下で抑制:
- Question生成しない
- Prompt短縮
- Output短縮
- Daily limit（主要アプリ制御）
- REQUEST + USAGEのDynamoDB Transaction
- Idempotency / same-practiceId Transport Retry
- Reserved Concurrency
- DynamoDB Maximum Throughput

DynamoDB Maximum Throughputはbest-effort targetであり、burst capacityにより一時的に超える可能性があるためHard Cost Capとはみなさない。

---

## 参照公式ドキュメント

- [DynamoDB - On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [DynamoDB - Maximum throughput for on-demand tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html)
- [Amazon Bedrock - Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [Amazon Nova 2 - Using tools](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-tools.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

