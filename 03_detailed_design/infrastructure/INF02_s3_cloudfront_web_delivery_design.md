---
document_id: DD-INF-002
title: "Infrastructure詳細設計 INF02 S3・CloudFront Web配信設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. S3

- Regular S3 Bucket origin
- Website hosting無効
- Block Public Access ON
- Object Ownershipは推奨設定
- Encryption at rest
- Versioningは静的配信では任意

# 2. OAC

CloudFront Origin Access Controlを使用。
OAIは新規採用しない。

Bucket Policy:
- Principal: cloudfront.amazonaws.com
- SourceArnを対象Distributionへ制限

# 3. Build

```text
next build
↓
out/
↓
S3
```

# 4. `trailingSlash`

Next:
```ts
trailingSlash: true
```

生成:
```text
/practice/index.html
```

# 5. URL Rewrite

CloudFront Default Root Objectだけではサブディレクトリを解決しない。

Viewer Request CloudFront Function:
- `/` -> `/index.html`はDefault Rootでも可
- URI ending `/` -> `${uri}index.html`
- extensionなしの扱いはNext outputと整合させる

# 6. Cache Policy

HTML:
- short cache / revalidation重視

`/_next/static/*`:
- long immutable cache

`sw.js`:
- `no-cache, no-store, must-revalidate`

Question Bank:
- versioned file名ならlong cache可

# 7. Security Headers

CloudFront Response Headers Policy:
- Strict-Transport-Security
- X-Content-Type-Options
- Referrer-Policy
- Content-Security-Policy
- Permissions-Policy
- Clickjacking対策（`frame-ancestors 'none'`）

## CSP方針

Next.js Static Export + S3/CloudFrontではrequestごとのnonceを生成できない。
MUI公式もStatic Websiteではnonceを利用できず、inline style/scriptの許可が必要になるケースを示している。
MVPではexperimental SRIへ依存せず、Static構成を維持する。

production baseline例:
```text
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
font-src 'self';
connect-src 'self' https://<http-api-host> https://cognito-idp.<region>.amazonaws.com;
worker-src 'self';
manifest-src 'self';
object-src 'none';
base-uri 'self';
form-action 'self';
frame-ancestors 'none';
```

ルール:
- productionで`unsafe-eval`禁止
- third-party scriptは原則追加しない
- script追加時はSecurity Review必須
- `connect-src`は実環境のAPI/Cognito endpointだけallowlist
- `dangerouslySetInnerHTML`禁止
- CSP Report-Onlyで事前検証後にenforceしてよい

Strict nonce CSPが必須になった場合、Static Exportを維持したまま無理に実現せずRuntime Rendering/BFFをADRで比較する。

# 8. Error

404:
- `/404.html`

SPA fallbackで全404をindex.htmlへ戻す方式は、
Static Exportの実routeエラーを隠しやすいため原則採用しない。

# 9. TLS

Viewer:
HTTPS redirectまたはHTTPS only。

# 10. Domain

TBD。
独自ドメイン採用時:
- Route 53 or external DNS
- ACM certificate
- CloudFront certificateはus-east-1要件を公式で再確認

# 11. Deployment

- S3 sync with delete慎重
- CloudFront invalidationはHTML/SW中心
- hashed static assetsは全invalidate不要

# 12. API Origin

MVPの基本はBrowserからHTTP APIへ直接。

将来`/api/*`をCloudFront経由にする場合は:
- Origin bypass
- CORS
- WAF
- custom domain
を一体で再設計する。

---

## 参照公式ドキュメント

- [CloudFront - Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [CloudFront - Default root object](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DefaultRootObject.html)
- [Next.js - Static Exports](https://nextjs.org/docs/app/guides/static-exports)
- [Next.js - Content Security Policy](https://nextjs.org/docs/app/guides/content-security-policy)
- [MUI - Content Security Policy](https://mui.com/material-ui/guides/content-security-policy/)
- [Next.js - Progressive Web Apps](https://nextjs.org/docs/app/guides/progressive-web-apps)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

