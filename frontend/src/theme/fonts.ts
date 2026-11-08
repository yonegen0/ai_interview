/** @file fonts.ts @description 実画面とStorybook共通のWebフォント定義 */
import { Inter, Noto_Sans_JP } from "next/font/google";

export const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const notoSansJP = Noto_Sans_JP({
  display: "swap",
  preload: false,
  variable: "--font-noto-sans-jp",
});
