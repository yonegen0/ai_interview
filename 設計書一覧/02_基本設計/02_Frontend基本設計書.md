# Frontend基本設計書

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 技術・現在地

Next.js / React / TypeScript / App Router / MUI styled / TanStack Query /
React Hook Form＋Zod / Storybook / MSW / Vitest / Playwright。
Node.js 22以上。CIも22を使用する。v2.0のNode.js v24.14.1／npm 11.11.0は当時の確認環境であり、必須バージョンではない。

現Frontendは認証なしのMSW単体MVP。PWA・実AI・実Backend・AWS公開は未実装。
[ADR-002](../../docs/ADR-002-frontend-contract-alignment.md)に従い、既存主要フローと復旧を維持する。

## 2. 構成・規約

- appはStatic Route Entry／Layout、操作はClient Feature。
- Page → Template → Organism → Molecule → Atom。Feature固有画面はfeatures配下。
- API Clientはsrc/lib/api、型・制約の正本はsrc/lib/api/schemas。配置を移動しない。
- TanStack Queryは通信、React Hook Form＋Zodは入力、Reducerは操作段階、sessionStorageは復旧情報。
- Componentから直接fetchしない。API ResponseはZodでRuntime Validation。
- JSDoc、Alias @/*、MUI styledを使用。sx／React.FC／anyは禁止。
- 回答・評価本文をHTMLとして描画しない。

## 3. Backend接続

[API契約](../../docs/FRONTEND_API_CONTRACT.md)の6 Route、全POSTのIdempotency-Key、
202受付と評価GET、100点評価を採用する。開発・テストはMSW、結合・本番は実APIを使う。
Access TokenのAuthorization Bearer付与・更新、認証切れ・ログアウト処理は次工程。
Base URL変更だけでは接続完了にならない。

## 4. Static Export

output: 'export'、trailingSlash: true。本番out/、Mock検証out-mock/。
将来の配信はPrivate S3＋CloudFront OAC、URL RewriteはCloudFront Functionで扱う。
PWA Service Workerやオフラインキャッシュは今回追加しない。
