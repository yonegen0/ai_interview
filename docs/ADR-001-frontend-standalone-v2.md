# ADR-001: Frontend単体MVPにv2契約を採用

状態: ユーザー承認済み実装計画に基づく採用。日付: 2026-09-08。

## 判断

FrontendをMSWで先行実装し、練習開始から結果・再挑戦までを完成させます。S3静的配信を維持します。

| 既存v1.1設計 | Frontend単体MVPの採用方針 |
|---|---|
| POST /v1/practicesによる同期評価 | Session/Attempt/Evaluationと非同期GET |
| practiceIdによる再送 | 全変更APIのIdempotency-Key |
| S/A/B/C、goodPoint等 | 0〜100 Score、summary、配列の改善点等 |
| Git Canonical Question Bankの配布 | 今回はMock APIが固定21問を返す |
| v2例の動的URL | 静的ルート＋sessionId/attemptIdクエリ |
| 認証・履歴・PWA等を含む全体MVP | 今回は主要練習フローのみ |

既存の計画・基本設計・詳細設計は将来の全体構想として保持します。今回のFrontend実装と矛盾する箇所は、このADRと[API契約](FRONTEND_API_CONTRACT.md)を優先します。

## 実装への影響

- 実Backend接続には新契約への対応または明示的な変換層が必要です。旧BackendへのURL差し替えだけでは接続できません。
- 状態管理にTanStack Queryを追加し、ローカルの入力と操作段階を分離します。
- Mockのタブ内保存は開発・検証用です。認証・本番保存・実AI評価は未実装です。
- 本番ビルドとMock静的ビルドを分け、本番成果物からWorkerを除きます。
- AWSデプロイは今回実施しません。
