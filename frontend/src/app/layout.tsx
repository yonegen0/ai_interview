/**
 * @file layout.tsx
 * @description アプリ全体のメタデータとMUIテーマを提供するルートレイアウト
 */
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { AppRouterCacheProvider } from "@mui/material-nextjs/v15-appRouter";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Interview Pocket | 3分でできるAI面接練習",
  description: "スキマ時間に一問ずつ取り組めるAI面接練習アプリ",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f5f2ea",
};

/** ルートレイアウトのProps */
type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

/**
 * 全ページに共通テーマと基本スタイルを提供する
 * @param props 配下に表示するページ
 * @returns アプリのルートHTML
 */
export default function RootLayout(props: RootLayoutProps) {
  return (
    <html lang="ja">
      <body>
        <AppRouterCacheProvider>
          <ThemeProvider theme={theme}>
            <CssBaseline />
            {props.children}
          </ThemeProvider>
        </AppRouterCacheProvider>
      </body>
    </html>
  );
}
