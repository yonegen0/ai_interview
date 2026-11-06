/** @file cognito.ts @description Cognitoの公開認証API adapter。OTP送信の自動再試行を行わない。 */
import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  RespondToAuthChallengeCommand,
  RevokeTokenCommand,
  NotAuthorizedException,
  UserNotFoundException,
  // InvalidParameterException does not prove the refresh token was revoked.
  type AuthenticationResultType,
} from "@aws-sdk/client-cognito-identity-provider";

export interface IdentityAdapter {
  begin(email: string): Promise<string>;
  complete(
    email: string,
    session: string,
    code: string,
  ): Promise<AuthenticationResultType>;
  refresh(token: string): Promise<AuthenticationResultType>;
  revoke(token: string): Promise<void>;
}
/** Only credential-rejection responses may invalidate saved refresh credentials. */
export function isRefreshCredentialRejected(error: unknown): boolean {
  return error instanceof NotAuthorizedException ||
    error instanceof UserNotFoundException;
}
/** Retry recognized transport, throttling and server-side transient failures only. */
export function isTransientRefreshError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as {
    name?: unknown;
    $retryable?: unknown;
    $metadata?: { httpStatusCode?: number };
  };
  const status = value.$metadata?.httpStatusCode;
  return value.$retryable != null ||
    (typeof status === "number" && (status === 429 || status >= 500)) ||
    (typeof value.name === "string" &&
      ["AbortError", "TimeoutError", "NetworkingError", "NetworkError",
        "RequestTimeout", "TypeError", "InternalErrorException",
        "TooManyRequestsException"].includes(value.name));
}
export function cognitoAdapter(): IdentityAdapter {
  const region = process.env.NEXT_PUBLIC_COGNITO_REGION;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
  const pool = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID;
  const endpoint = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (
    !region ||
    !clientId ||
    !pool?.startsWith(`${region}_`) ||
    !endpoint?.startsWith("https://")
  )
    throw new Error("認証の接続設定を確認してください。");
  const client = new CognitoIdentityProviderClient({ region, maxAttempts: 1 });
  async function call<T>(operation: (signal: AbortSignal) => Promise<T>) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      return await operation(controller.signal);
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    async begin(email) {
      let result = await call((signal) =>
        client.send(
          new InitiateAuthCommand({
            ClientId: clientId,
            AuthFlow: "USER_AUTH",
            AuthParameters: {
              USERNAME: email,
              PREFERRED_CHALLENGE: "EMAIL_OTP",
            },
          }),
          { abortSignal: signal },
        ),
      );
      if (result.ChallengeName === "SELECT_CHALLENGE")
        result = await call((signal) =>
          client.send(
            new RespondToAuthChallengeCommand({
              ClientId: clientId,
              ChallengeName: "SELECT_CHALLENGE",
              Session: result.Session,
              ChallengeResponses: { USERNAME: email, ANSWER: "EMAIL_OTP" },
            }),
            { abortSignal: signal },
          ),
        );
      if (result.ChallengeName !== "EMAIL_OTP" || !result.Session)
        throw new Error("メールコードでのログインを開始できませんでした。");
      return result.Session;
    },
    async complete(email, session, code) {
      const result = await call((signal) =>
        client.send(
          new RespondToAuthChallengeCommand({
            ClientId: clientId,
            ChallengeName: "EMAIL_OTP",
            Session: session,
            ChallengeResponses: { USERNAME: email, EMAIL_OTP_CODE: code },
          }),
          { abortSignal: signal },
        ),
      );
      if (!result.AuthenticationResult)
        throw new Error("ログインを完了できませんでした。");
      return result.AuthenticationResult;
    },
    async refresh(token) {
      const result = await call((signal) =>
        client.send(
          new InitiateAuthCommand({
            ClientId: clientId,
            AuthFlow: "REFRESH_TOKEN_AUTH",
            AuthParameters: { REFRESH_TOKEN: token },
          }),
          { abortSignal: signal },
        ),
      );
      if (!result.AuthenticationResult)
        throw new Error("ログインを更新できませんでした。");
      return result.AuthenticationResult;
    },
    async revoke(token) {
      await call((signal) =>
        client.send(
          new RevokeTokenCommand({ ClientId: clientId, Token: token }),
          { abortSignal: signal },
        ),
      );
    },
  };
}
