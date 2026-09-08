---
document_id: DD-BE-006
title: "Backend詳細設計 BE06 Question Bank・出題ロジック設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 目的

質問生成をAIから切り離し、品質・速度・コスト・再現性を確保する。

# 2. Format

```json
{
  "version": "questions-v1",
  "questions": [
    {
      "id": "job_change_001",
      "category": "job_change",
      "question": "なぜ転職しようと思ったのですか？",
      "enabled": true
    }
  ]
}
```

# 3. ID

`questionId`は公開後に再利用しない。

例:
- `job_change_001`
- `motivation_001`
- `self_pr_001`

文言修正で意味が変わる場合は新IDまたはQuestion Bank version更新を検討する。

# 4. Category

固定enum:
- job_change
- motivation
- self_pr
- experience
- difficulty
- career_plan
- questions

Frontend/Backendで共有型を持つ。

# 5. 初期配分

- 転職理由 15
- 志望動機 15
- 自己PR 15
- 仕事経験 20
- 困難/失敗 15
- キャリアプラン 10
- 逆質問 10

合計約100。

# 6. 配布

Git上の単一Canonical Sourceを正とする。

```text
resources/question-bank/
  questions-v1.json
  questions-v2.json
  manifest.json
```

Build時に生成:
```text
Canonical Source
  ├─ Frontend artifact: current version
  └─ Backend artifact: current + previous version
```

ルール:
- Frontend/BackendへJSONを手作業コピーしない
- `manifest.json`にcurrent versionと各file hashを保持する
- CIでSchema、questionId重複、version、hashを検証する
- 生成物はbuild artifactとして扱い、正データは`resources/question-bank/`のみ

# 7. Backend Validation

POST practices:
- version support確認
- question id存在
- enabled
- category/本文はServer側値を使用

Client送信のquestion本文を信用しない。

# 8. Frontend Selection

カテゴリ選択後:

```text
all category questions
  ↓
enabled
  ↓
unanswered first
  ↓
exclude recent N
  ↓
random
```

# 9. 回答済み判定

履歴の`questionId + questionBankVersion`を利用。

同じIDがversion間で意味を維持する場合はIDだけでanswered扱いにするか、
versionごとに扱うかをQuestion変更ルールで統一する。

MVP推奨:
- questionIdが同じなら回答済みと扱う

# 10. Recent Avoidance

初期候補:
- 直近5問を除外

候補不足なら除外数を緩和。

# 11. All Completed

カテゴリ内を全て回答済みの場合:
- 最終回答日時が古い順を優先する、または
- 再シャッフル

MVP推奨:
「古い回答から再挑戦」を優先し、成長比較につなげる。

# 12. Version Compatibility

Backend:
- current
- previous

を最低限一定期間サポートできる配置。

unsupported:
`QUESTION_BANK_VERSION_UNSUPPORTED`

Frontend:
- SW update確認
- Reload案内

# 13. Review

Question Bank公開前:
- 重複
- Yes/Noだけで終わる質問
- 曖昧すぎる質問
- 特定業界依存
- 不適切/センシティブ
- カテゴリ誤り

を人がレビューする。

# 14. 将来

将来AI生成Questionを追加する場合も、
MVPのQuestion Bankを消さず別modeとして追加する。
