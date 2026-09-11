# S3・CloudFront詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. S3
Private Bucket。
Static Website Public Hostingは使用しない。

## 2. CloudFront
OACでS3へアクセス。

## 3. CloudFront Function
[Frontend配信詳細](../Frontend/05_PWA_StaticExport_配信詳細設計.md)の全静的Routeを対象にURIをRewriteする。
/ → /index.html、/practice と末尾/付き → /practice/index.html、
/practice/session と末尾/付き → /practice/session/index.html、
/result と末尾/付き → /result/index.html。
クエリのsessionId／attemptId／mode／fromAttemptIdは維持し、asset URIは変更しない。
trailingSlash: trueとの整合、直接アクセス・再読み込みを配信工程で検証する。

## 4. ACM
CloudFront Certificateはus-east-1。

## 5. Cache
HTMLとstatic assetsのCache Policyを分ける。
Deploy後のInvalidation方針をCI/CD設計で定める。
