/** @file AppProviders.tsx @description Theme・Query・Mock起動境界 */
"use client";
import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Alert from "@mui/material/Alert";
import { theme } from "@/theme/theme";
import { retryGet } from "@/lib/api/client";
import { storageAvailable, subscribeStorage } from "@/lib/storage/recovery";
export const mockEnabled = process.env.NEXT_PUBLIC_MSW_ENABLED === "true";
export const createAppQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: retryGet,
        staleTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
const StorageNotice = () => {
  const available = useSyncExternalStore(
    subscribeStorage,
    storageAvailable,
    () => true,
  );
  return available ? null : (
    <Alert severity="warning">
      保存領域を利用できません。再読み込み後の復元はできません。
    </Alert>
  );
};
export const AppProviders = ({ children }: { children: ReactNode }) => {
  const [client] = useState(createAppQueryClient);
  const [ready, setReady] = useState(!mockEnabled);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (mockEnabled) {
      let active = true;
      import("@/mocks/browser")
        .then((m) => m.startMock())
        .then(() => {
          if (active) setReady(true);
        })
        .catch(() => {
          if (active) setError(true);
        });
      return () => {
        active = false;
      };
    }
  }, []);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={client}>
        <StorageNotice />
        {mockEnabled && (
          <Alert severity="info">
            体験版：評価は固定サンプルです。実際のAI評価ではありません。
          </Alert>
        )}
        {error ? (
          <Alert severity="error">
            Mockを起動できませんでした。ページを再読み込みしてください。
          </Alert>
        ) : ready ? (
          children
        ) : (
          <p role="status">練習環境を準備しています…</p>
        )}
      </QueryClientProvider>
    </ThemeProvider>
  );
};
