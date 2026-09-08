---
document_id: DD-INF-004
title: "Infrastructure詳細設計 INF04 Cognito・SES設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. Cognito Tier

Passwordless Email OTPを利用可能なTierを採用する。
現時点ではEssentials以上を前提とする。

# 2. User Pool

- Self sign-up disabled
- Username/sign-in: email
- SignInPolicy EMAIL_OTP
- Required MFAなし
- Account recoveryはPasswordless構成と整合確認

# 3. App Client

- GenerateSecret=false
- `ALLOW_USER_AUTH`
- `PreventUserExistenceErrors=ENABLED`
- Token revocation有効を確認
- Token validityはUX/リスクから決定

# 4. Groups

`USER`
`ADMIN`

CDKで作成する。

# 5. User Creation

AdminCreateUser:
- TemporaryPasswordなし
- MessageAction=SUPPRESS
- email attributes
- Group USER

PROFILEはDynamoDB。

# 6. SES

CognitoのEmail sending accountをSESへ設定。

確認:
- SES Region
- verified identity/domain
- FROM
- Production access
- Sending quota
- bounce/complaint monitoring

# 7. Email Content

OTPメールは短くする。

含める:
- サービス名
- 認証コード
- 有効時間に関する一般説明
- 心当たりがない場合は無視

機密情報や求職者の面接内容を含めない。

# 8. Enumeration

`PreventUserExistenceErrors=ENABLED`。

Frontendも:
- 「未登録です」
- 「このメールは存在しません」

と明示しない。

# 9. Monitoring

- Cognito sign-in failure傾向
- SES send/bounce/complaint
- メール送信障害

# 10. User Disable / Token Revocation

管理APIのDisableでは以下へ状態収束する。
1. DynamoDB `PROFILE.status=DISABLED`
2. Cognito `AdminDisableUser`
3. Cognito `AdminUserGlobalSignOut`

`AdminUserGlobalSignOut`は対象ユーザーのrefresh / ID / access tokenを取り消す。
ただし自己完結JWTの署名/expだけを検証する経路ではrevocationを即時検知できないため、API側`PROFILE.status` gateを必須とする。

# 11. Cost

Cognito/SES pricingはdeploy前に公式料金で確認。
設計はFree Tierの存在を前提に壊れないようにする。

---

## 参照公式ドキュメント

- [Amazon Cognito - Authentication flows / Passwordless](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html)
- [Amazon Cognito - Managing user existence error responses](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-managing-errors.html)
- [Amazon Cognito - AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)
- [Amazon Cognito - UserPoolClientType](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_UserPoolClientType.html)
- [Amazon Cognito - Token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

