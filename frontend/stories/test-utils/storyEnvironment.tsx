/** @file storyEnvironment.tsx @description Query、Storage、RouterをStoryごとに隔離する共通環境。 */
import { useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getRouter, useSearchParams } from "@storybook/nextjs-vite/navigation.mock";
import type { MockState } from "@/mocks/store";

export type StoryMockScenario =
  | "success"
  | "slow"
  | "never"
  | "validation"
  | "unauthorized"
  | "not_found"
  | "server_error"
  | "network_error"
  | "response_lost"
  | "invalid_response"
  | "evaluation_failed"
  | "state_conflict";

export type FeatureStoryParameters = {
  mock?: boolean;
  mockScenario?: StoryMockScenario;
  initialRoute?: string;
  seed?: MockState;
  storage?: Record<string, unknown>;
};

export const createStoryQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });

export const StoryQueryProvider = (props: { children: ReactNode }) => {
  const [client] = useState(createStoryQueryClient);
  useEffect(
    () => () => {
      void client.cancelQueries();
      client.clear();
    },
    [client],
  );
  return <QueryClientProvider client={client}>{props.children}</QueryClientProvider>;
};

const pocketKeys = ["pocket:mock:v1", "pocket:scenario", "pocket:create"];
const pocketPrefixes = ["pocket:answer:", "pocket:next:"];

export const clearPocketStorage = (): void => {
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index);
    if (key && (pocketKeys.includes(key) || pocketPrefixes.some((prefix) => key.startsWith(prefix)))) {
      sessionStorage.removeItem(key);
    }
  }
};

export const setInitialRoute = (path: string): void => {
  const url = new URL(path, "http://storybook.local");
  useSearchParams.mockReturnValue(
    new URLSearchParams(url.search) as unknown as ReturnType<
      typeof useSearchParams
    >,
  );
};

export const resetNavigationMock = (): void => {
  const router = getRouter();
  router.push.mockReset();
  router.replace.mockReset();
  router.back.mockReset();
  router.forward.mockReset();
  router.refresh.mockReset();
  router.prefetch.mockReset();
  useSearchParams.mockReset();
  useSearchParams.mockReturnValue(
    new URLSearchParams() as unknown as ReturnType<typeof useSearchParams>,
  );
};

export const assertNoHorizontalOverflow = (element: HTMLElement): void => {
  if (element.scrollWidth > element.clientWidth) {
    throw new Error(`Horizontal overflow: ${element.scrollWidth} > ${element.clientWidth}`);
  }
};
