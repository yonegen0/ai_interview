/** @file cognito-adapter.test.ts @description Cognito command形状・EMAIL_OTP選択・再試行禁止。 */
import { beforeEach, expect, it, vi } from "vitest";
const sdk = vi.hoisted(() => ({ send: vi.fn(), configuration: vi.fn() }));
vi.mock("@aws-sdk/client-cognito-identity-provider", () => {
  class Command {
    constructor(public input: unknown) {}
  }
  return {
    CognitoIdentityProviderClient: class {
      constructor(configuration: unknown) {
        sdk.configuration(configuration);
      }
      send = sdk.send;
    },
    InitiateAuthCommand: Command,
    RespondToAuthChallengeCommand: Command,
    RevokeTokenCommand: Command,
  };
});
import { cognitoAdapter } from "@/lib/auth/cognito";
beforeEach(() => {
  sdk.send.mockReset();
  sdk.configuration.mockReset();
  vi.stubEnv("NEXT_PUBLIC_COGNITO_REGION", "ap-northeast-1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID", "ap-northeast-1_synthetic");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "synthetic-client");
  vi.stubEnv(
    "NEXT_PUBLIC_API_BASE_URL",
    "https://synthetic.execute-api.ap-northeast-1.amazonaws.com/dev",
  );
});
it("requests EMAIL_OTP and handles SELECT_CHALLENGE", async () => {
  sdk.send
    .mockResolvedValueOnce({
      ChallengeName: "SELECT_CHALLENGE",
      Session: "first",
    })
    .mockResolvedValueOnce({ ChallengeName: "EMAIL_OTP", Session: "email" });
  expect(await cognitoAdapter().begin("user@example.invalid")).toBe("email");
  expect(sdk.configuration).toHaveBeenCalledWith({
    region: "ap-northeast-1",
    maxAttempts: 1,
  });
  expect(sdk.send.mock.calls[0][0].input).toMatchObject({
    AuthFlow: "USER_AUTH",
    AuthParameters: {
      USERNAME: "user@example.invalid",
      PREFERRED_CHALLENGE: "EMAIL_OTP",
    },
  });
  expect(sdk.send.mock.calls[1][0].input).toMatchObject({
    ChallengeName: "SELECT_CHALLENGE",
    Session: "first",
    ChallengeResponses: {
      USERNAME: "user@example.invalid",
      ANSWER: "EMAIL_OTP",
    },
  });
});
it("submits code, refreshes and revokes without any client secret", async () => {
  const result = { AccessToken: "synthetic", ExpiresIn: 300 };
  sdk.send.mockResolvedValue({ AuthenticationResult: result });
  const adapter = cognitoAdapter();
  expect(
    await adapter.complete("user@example.invalid", "challenge", "123456"),
  ).toEqual(result);
  expect(sdk.send.mock.calls[0][0].input).toMatchObject({
    ChallengeName: "EMAIL_OTP",
    ChallengeResponses: {
      USERNAME: "user@example.invalid",
      EMAIL_OTP_CODE: "123456",
    },
    Session: "challenge",
  });
  await adapter.refresh("synthetic-refresh");
  expect(sdk.send.mock.calls[1][0].input).toMatchObject({
    AuthFlow: "REFRESH_TOKEN_AUTH",
    AuthParameters: { REFRESH_TOKEN: "synthetic-refresh" },
  });
  await adapter.revoke("synthetic-refresh");
  expect(sdk.send.mock.calls[2][0].input).toEqual({
    ClientId: "synthetic-client",
    Token: "synthetic-refresh",
  });
});
it("fails missing configuration before any SDK send", () => {
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "");
  expect(() => cognitoAdapter()).toThrow("接続設定");
  expect(sdk.send).not.toHaveBeenCalled();
});
