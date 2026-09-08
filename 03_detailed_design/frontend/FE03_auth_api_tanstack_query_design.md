---
document_id: DD-FE-003
title: "Frontend詳細設計 FE03 認証・API・TanStack Query設計"
version: "1.1"
status: "Draft"
updated_at: "2026-09-08"
project: "AI面接練習Webアプリ MVP"
---

# 1. 認証ライブラリ

MVPではAWS公式のAmplify Auth client moduleを第一候補とする。
Amplify Hostingは使用しない。

`shared/auth/authClient.ts`に閉じ込める。

# 2. Auth Client Interface

```ts
export type AuthClient = {
  requestEmailOtp(email: string): Promise<void>;
  confirmEmailOtp(code: string): Promise<void>;
  getAccessToken(): Promise<string | null>;
  getCurrentUser(): Promise<AuthUser | null>;
  signOut(): Promise<void>;
};
```

FeatureはAmplify固有APIを知らない。

# 3. Email OTP Flow

```text
signIn({
  username: email,
  options: {
    authFlowType: "USER_AUTH",
    preferredChallenge: "EMAIL_OTP"
  }
})
↓
CONFIRM_SIGN_IN_WITH_EMAIL_CODE
↓
confirmSignIn({ challengeResponse: otp })
↓
DONE
```

予期しないNextStepはAuthErrorへ変換する。

# 4. Token

APIにはAccess Tokenのみ送信。

```http
Authorization: Bearer <access token>
```

ID TokenをAPI認可に使用しない。

# 5. Token Storage

MVP標準はAmplify Token Provider + Browser `sessionStorage`。

```ts
import { cognitoUserPoolsTokenProvider } from "aws-amplify/auth/cognito";
import { sessionStorage } from "aws-amplify/utils";

cognitoUserPoolsTokenProvider.setKeyValueStorage(sessionStorage);
```

ルール:
- Local StorageをMVP標準にしない
- Tokenを独自IndexedDBへ複製しない
- Service Worker Cacheへ入れない
- third-party scriptを原則追加しない
- `dangerouslySetInnerHTML`禁止
- CSPを併用する

`sessionStorage`も実行中XSSからTokenを完全保護する仕組みではない。
Strict nonce CSP / HttpOnly Cookieが必要になった場合はStatic Exportを含めBFF/Runtime構成へADR変更する。

# 6. apiClient

```ts
type ApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
};

export const apiClient = async <T>(
  path: string,
  options?: ApiRequestOptions,
): Promise<T> => { /* ... */ };
```

責務:
- baseUrl
- access token
- headers
- JSON
- error normalization
- timeout

# 7. Timeout

目安:
- Normal GET/PATCH: 10s
- AI POST: 20s

値は定数化する。
AI POSTの自動retryは行わない。

ただしHTTP timeout / response lost後にユーザーが再試行する場合は、送信済みの同一`practiceId`を再利用する。
Backendから`PRACTICE_FAILED`が確定した場合に限り、「新しい練習」で新`practiceId`を生成する。

# 8. ApiError

```ts
export type ApiErrorCode =
  | "VALIDATION_ERROR"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "ACCOUNT_DISABLED"
  | "NOT_FOUND"
  | "PRACTICE_PROCESSING"
  | "PRACTICE_FAILED"
  | "DAILY_LIMIT_EXCEEDED"
  | "RATE_LIMITED"
  | "AI_RESPONSE_INVALID"
  | "AI_UNAVAILABLE"
  | "QUESTION_BANK_VERSION_UNSUPPORTED"
  | "NETWORK_ERROR"
  | "UNKNOWN";
```

`ACCOUNT_DISABLED`ではlocal auth stateを破棄し、現在subのIndexedDB cacheを削除して`/login`へ遷移する。

# 9. Query Keys

```ts
export const queryKeys = {
  me: ["me"] as const,
  practices: (filters: PracticeFilters) =>
    ["practices", filters] as const,
  favorites: ["favorites"] as const,
  adminUsers: (filters: AdminUserFilters) =>
    ["admin", "users", filters] as const,
  adminUser: (userId: string) =>
    ["admin", "user", userId] as const,
};
```

# 10. Query Defaults

GET:
- retry: 1程度
- staleTimeは画面特性に合わせる

AI Mutation:
- `retry: false`
- timeout後のユーザー再試行はmutation inputに保持した同一`practiceId`を使用

Favorite:
- 自動retryを限定的に許容してもよいが、Backend Conditional Updateで冪等性を確保する

# 11. Mutation後更新

Practice成功:
- history invalidate
- me invalidate
- IndexedDBへ保存

Favorite成功:
- practice/favorite cache更新
- favorites invalidate
- me invalidate
- IndexedDB更新

# 12. Auth Error

401:
1. `fetchAuthSession`によるrefreshをライブラリへ任せる
2. それでもtoken取得不可ならLogout state
3. `/login`へ遷移

無限refresh loopを作らない。

# 13. Offline

`navigator.onLine`だけを絶対視しない。
API network failureもOffline表示へ反映する。

AI送信Button:
- Offline時disabled
- 「AI評価には通信が必要です」を表示

---

## 参照公式ドキュメント

- [AWS Amplify - Switching authentication flows](https://docs.amplify.aws/react/frontend/auth/switching-authentication-flows/)
- [AWS Amplify - Tokens and credentials](https://docs.amplify.aws/react/build-a-backend/auth/concepts/tokens-and-credentials/)
- [API Gateway - HTTP API JWT authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)

> 情報確認日: 2026-09-08。ライブラリ/API/モデルID/料金は実装時にも公式ドキュメントで再確認すること。

