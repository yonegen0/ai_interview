---
document_id: DD-BE-003
title: "Backend詳細設計 BE03 Cognito認証・認可・ユーザー管理設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. User Pool

要件:
- Passwordless Email OTP
- Self sign-up disabled
- Admin create only
- Cognito Essentials以上
- Required MFAなし

# 2. SignInPolicy

```json
{
  "AllowedFirstAuthFactors": ["EMAIL_OTP"]
}
```

# 3. App Client

- Public client
- GenerateSecret=false
- `ALLOW_USER_AUTH`
- Refresh token authは利用ライブラリ/設定と合わせる
- `PreventUserExistenceErrors=ENABLED`

# 4. Groups

- USER
- ADMIN

認可の正データ。

# 5. User Attributes

必須は最小限にする。

推奨:
- Cognito username/sign-in: email
- email
- email_verified

氏名の正データはDynamoDB PROFILEを基本とする。

# 6. Login

Frontend:
`USER_AUTH` + `EMAIL_OTP`

Cognito:
- email OTP送信
- challenge確認
- token発行

未登録ユーザーの存在をUI上で露出しない。

# 7. API Authorization

API Gateway JWT Authorizer:
- issuer
- audience（App Client ID）
- signature
- exp / nbf / iat等

API Gatewayは`aud`がなければ`client_id`をaudienceと照合するが、JWT AuthorizerにはAccess TokenとID Tokenを標準的に区別する仕組みがない。
そのため全保護routeでLambda共通Auth Guardを実行する。

Lambda Auth Guard:
1. `token_use == "access"`
2. `client_id == EXPECTED_APP_CLIENT_ID`
3. `sub`が存在
4. `cognito:groups`を取得
5. DynamoDB `USER#{sub}/PROFILE`をStrongly Consistent Readし`status == ACTIVE`を確認
6. ADMIN routeでは`ADMIN ∈ cognito:groups`

失敗:
- token claim不正: `401 UNAUTHORIZED`
- Group不足: `403 FORBIDDEN`
- PROFILE disabled: `403 ACCOUNT_DISABLED`

USER APIでClient指定userIdを本人判定に使用せず、認証済み`sub`を正とする。

# 8. Access Token

API認可はAccess Tokenのみを使用し、ID Tokenを認可用途に使用しない。

Cognito Access Tokenで必須確認するclaims:
```text
token_use = access
client_id = EXPECTED_APP_CLIENT_ID
sub = <user id>
cognito:groups = [...]
```

Cognito API認証（`USER_AUTH` / `InitiateAuth`系）で発行されるAccess Tokenの`scope`は通常`aws.cognito.signin.user.admin`のみとなる。
したがってMVPでは独自API用custom scopeをroute authorizationへ採用しない。

将来、Managed Login/OAuth authorization serverまたはPre Token Generationでcustom scopeを正式導入する場合だけ、route scope方式を別ADRで検討する。

# 9. AdminCreateUser

Input:
- name
- email

Cognito:
- TemporaryPassword省略
- Passwordless user
- MessageAction=SUPPRESSを基本
- AdminAddUserToGroup(USER)

利用URLは業務連絡で案内。

# 10. 部分失敗

Cognito/DynamoDB間に分散Transactionはない。

処理を状態収束型にする。

例:
1. emailからCognito user確認
2. なければcreate
3. group確認/追加
4. PROFILE確認/作成
5. すべて成立したら成功

既存userが途中状態でも再実行で完成できる。

# 11. Disable

ADMIN Disableは、発行済JWTの署名/exp検証だけでは即時失効を検知できない点を前提にする。

順序:
1. `PROFILE.status=DISABLED`（アプリAPIを即時denyするため先行）
2. `AdminDisableUser`
3. `AdminUserGlobalSignOut`

Enable:
1. `AdminEnableUser`
2. `PROFILE.status=ACTIVE`

Cognito/DynamoDB間にTransactionはないため、管理APIは冪等に再実行可能とする。
途中失敗時は最終的に上記状態へ収束させる。

# 12. Logout / Revocation

通常LogoutはFrontend `signOut`を使用する。
必要に応じて`signOut({ global: true })`をauthClient内部から利用できるようにする。

管理者停止は`AdminUserGlobalSignOut`を実行する。
ただしCognito User Pool JWTは自己完結型であり、取り消し後も署名/有効期限だけを検証する一般JWT検証ではvalidになり得るため、アプリAPIの即時停止は`PROFILE.status` gateを必須とする。

# 13. Security

- OTP/JWTをlogしない
- 未登録emailを推測しやすいErrorを返さない
- App Client SecretをFrontendへ置かない
- Refresh token lifetimeは運用/UXとリスクを見て設定

---

## 参照公式ドキュメント

- [Amazon Cognito - Authentication flows / Passwordless](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html)
- [Amazon Cognito - Managing user existence error responses](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-managing-errors.html)
- [Amazon Cognito - AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)
- [Amazon Cognito - UserPoolClientType](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_UserPoolClientType.html)
- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [Amazon Cognito - Understanding the access token](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Amazon Cognito - Ending user sessions with token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

