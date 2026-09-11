# Frontendアーキテクチャ詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. Layer

| 配置 | 責務 |
|---|---|
| src/app | Static Route Entry／Layout |
| src/features | home／interview／feedback。Feature固有のpages／templates／organisms／molecules |
| src/components | 共通templates／organisms／molecules／atoms |
| src/lib/api | API Client・各API関数 |
| src/lib/api/schemas | ZodのRequest／Response・型の正本 |
| src/lib/storage | 下書き・未確定操作の復旧保存 |
| src/providers | Query・Theme・Mock起動境界 |
| src/mocks | MSW Handler・質問・テストRepository |
| src/theme | 共通Theme |

依存方向はPage → Template → Organism → Molecule → Atom。
共通ComponentからFeature、下位Atomic層から上位層を参照しない。
新しいshared層や未使用の認証抽象化は追加しない。

## 2. 状態・API依存

Component → Hook／API関数 → API Client → fetch。
TanStack Queryは通信、React Hook Form＋Zodは入力、Reducerは操作段階を担当する。
sessionStorageはversion=1の下書き・未確定要求を保持する。既存保存形式を変更しない。
[API契約](../../../docs/FRONTEND_API_CONTRACT.md)を正本とし、Componentから直接fetchしない。

## 3. Mock切替・Error境界

Local／TestはMSW。Integration／Productionは認証実装後に実HTTP APIへ接続する。
本番ビルドはMock Workerを除去し、Mock静的成果物を公開用に扱わない。
Network／Auth／Validation／業務ErrorをAPI Clientで日本語表示へ正規化する。
未知codeは汎用表示、Backend本文は表示しない。
