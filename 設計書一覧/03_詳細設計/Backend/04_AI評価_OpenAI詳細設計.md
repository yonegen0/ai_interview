# AI評価・OpenAI詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. API
Responses API。1回完結のStateless評価。

## 2. 業務出力とFeedback

| 項目 | 業務上の制約 |
|---|---|
| score | 0〜100の整数 |
| summary | 文字列 |
| strengths | 文字列配列。空配列を許容 |
| improvements | 文字列配列。空配列を許容 |
| exampleAnswer | 任意の文字列 |

公開型は[Zod Schema](../../../frontend/src/lib/api/schemas/index.ts)を正本とする。
BackendでAI出力を検証してこの業務出力に組み立て、ID・日時・質問・回答など管理情報を補ってFeedbackとする。
旧ランク評価から点数への機械的換算は追加しない。
モデルへ渡すStructured Output SchemaとPydantic実装（任意項目の表現を含む）はBackend工程で公式仕様を確認する。
この表はSDK用JSON Schemaの実装例ではない。
受付POSTは202、評価GETはprocessing／completed／failed。AI結果を同期POST応答として返さない。

## 3. Prompt原則
- 事実を追加しない
- 必要以上に誇張しない
- 本人が面接で話せる自然さを優先
- Categoryごとの回答構成を評価基準へ反映
- Prompt Versionを保存

## 4. Data Control
`store=False`を明示。
Toolsなし。
API Data Sharing OFFを維持。

## 5. Model
第一候補GPT-5.6 Luna。
Luna low / Luna medium / Terra lowを実データで比較後に確定。
上記は設計時の比較候補名であり、APIモデルID・利用可否・認証方式・SDK互換性はBackend工程で公式確認する。
