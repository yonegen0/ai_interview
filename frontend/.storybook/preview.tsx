/**
 * @file .storybook/preview.tsx
 * @description Storybookのプレビュー画面におけるグローバル設定。
 */
import type { Preview } from "@storybook/nextjs-vite";
import { ThemeProvider } from "@mui/material/styles";
import { CssBaseline } from "@mui/material";
import { theme } from "../src/theme/theme";
import {
  clearPocketStorage,
  resetNavigationMock,
  setInitialRoute,
  StoryQueryProvider,
  type FeatureStoryParameters,
} from "../stories/test-utils/storyEnvironment";

/**
 * レスポンシブ確認用ビューポート。PC/スマホ境界 md=900 をまたぐ 4 つを定義する。
 */
const responsiveViewports = {
  iphoneSe: {
    name: "iPhone SE (375)",
    styles: { width: "375px", height: "667px" },
    type: "mobile" as const,
  },
  iphone14Pro: {
    name: "iPhone 14 Pro (393)",
    styles: { width: "393px", height: "852px" },
    type: "mobile" as const,
  },
  ipad: {
    name: "iPad (768)",
    styles: { width: "768px", height: "1024px" },
    type: "tablet" as const,
  },
  desktop: {
    name: "Desktop (1280)",
    styles: { width: "1280px", height: "800px" },
    type: "desktop" as const,
  },
};

/**
 * Storybook全体に適用されるレンダリング設定。
 */
const preview: Preview = {
  parameters: {
    nextjs: { appDirectory: true },
    a11y: { test: "error" },
    layout: "centered",
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    viewport: {
      options: responsiveViewports,
    },
  },
  loaders: [
    async ({ parameters }) => {
      const feature = parameters as FeatureStoryParameters & {
        handlers?: Parameters<(typeof import("../src/mocks/browser"))["worker"]["use"]>;
      };
      resetNavigationMock();
      clearPocketStorage();
      setInitialRoute(feature.initialRoute ?? "/");
      if (feature.mockScenario) {
        sessionStorage.setItem("pocket:scenario", feature.mockScenario);
      }
      for (const [key, value] of Object.entries(feature.storage ?? {})) {
        sessionStorage.setItem(key, JSON.stringify(value));
      }
      if (feature.mock) {
        const { startMock, worker, repository } =
          await import("../src/mocks/browser");
        await startMock();
        worker.resetHandlers();
        repository.reset();
        if (feature.seed) repository.write(feature.seed);
        if (feature.handlers) worker.use(...feature.handlers);
      }
      return {};
    },
  ],

  /**
   * 各ストーリーに MUI のテーマとベーススタイルを適用するためのデコレーター。
   */
  decorators: [
    (Story) => (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <StoryQueryProvider>
          <Story />
        </StoryQueryProvider>
      </ThemeProvider>
    ),
  ],
};

export default preview;
