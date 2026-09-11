# AI面接練習Webアプリ｜設計書 v2.1

更新日: 2026-09-11

現Frontendの契約と復旧を維持し、Backend実装・Terraform構築・実API接続へ進むための設計書体系です。
現在動作するのはMSW単体MVP。認証・実AI・Backend・AWS公開・PWAは次工程です。

## 読む順序

1. [設計書一覧](00_管理/00_設計書一覧.md)
2. [CHANGELOG](00_管理/01_CHANGELOG.md)
3. [ADR-002](../docs/ADR-002-frontend-contract-alignment.md)と[API契約](../docs/FRONTEND_API_CONTRACT.md)
4. [全体基本設計](02_基本設計/01_全体基本設計書.md)
5. [Backend基本設計](02_基本設計/03_Backend基本設計書.md)と[Infrastructure基本設計](02_基本設計/04_Infrastructure基本設計書.md)
6. [Backend着手前の必須事項](04_横断仕様/06_決定事項_未確定事項.md)

## 正本・未確定事項

型・制約は[Zod Schema](../frontend/src/lib/api/schemas/index.ts)、HTTP・復旧はAPI契約、
採用判断はADRを参照します。変更文書をv2.1とし、未変更のv2.0文書も継続する方針として扱います。
非同期起動方式・障害回復・物理データ設計は未確定であり、推測で補わず次工程で確定します。
モデル・OpenAI認証・SDK・Cognito・Lambda Runtime・Terraform Provider等の外部仕様は実装時に公式確認してください。
