# PWA・Static Export・配信詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。

## 1. 現状・Build

Next.js output: 'export'、trailingSlash: true。本番out/、Mock検証out-mock/。
PWA・オフラインキャッシュは未実装。MSW Workerは開発用であり、PWA実装ではない。
今回PWA Service WorkerやIndexedDBは追加しない。

## 2. Hosting・URL Rewrite

将来の配信はCloudFront → OAC → Private S3。
CloudFront FunctionでURIだけを以下へRewriteする。クエリのsessionId／attemptId／mode／fromAttemptIdは維持する。

| アクセスURI | S3オブジェクト |
|---|---|
| / | /index.html |
| /practice または /practice/ | /practice/index.html |
| /practice/session または /practice/session/ | /practice/session/index.html |
| /result または /result/ | /result/index.html |

静的assetをページへ書き換えない。未知Routeの扱いは配信工程で決定する。
実装時に全Routeの直接アクセス・再読み込みとtrailingSlashの整合を検証する。

## 3. Cache

HTMLとhashed static assetsでCache Policyを分離する。
ログイン・実API・オフライン保存のCache設計は次工程とし、認証データを静的キャッシュへ混在させない。
