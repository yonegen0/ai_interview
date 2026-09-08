/**
 * @file .storybook/preview.tsx
 * @description Storybookのプレビュー画面におけるグローバル設定。
 */
import type { Preview } from '@storybook/react-vite';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from '../src/lib/theme';

/**
 * レスポンシブ確認用ビューポート。PC/スマホ境界 md=900 をまたぐ 4 つを定義する。
 */
const responsiveViewports = {
  iphoneSe: {
    name: 'iPhone SE (375)',
    styles: { width: '375px', height: '667px' },
    type: 'mobile' as const,
  },
  iphone14Pro: {
    name: 'iPhone 14 Pro (393)',
    styles: { width: '393px', height: '852px' },
    type: 'mobile' as const,
  },
  ipad: {
    name: 'iPad (768)',
    styles: { width: '768px', height: '1024px' },
    type: 'tablet' as const,
  },
  desktop: {
    name: 'Desktop (1280)',
    styles: { width: '1280px', height: '800px' },
    type: 'desktop' as const,
  },
};

/**
 * Storybook全体に適用されるレンダリング設定。
 */
const preview: Preview = {
  parameters: {
    layout: 'centered',
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    viewport: {
      viewports: responsiveViewports,
      defaultViewport: 'desktop',
    },
  },

  /**
   * 各ストーリーに MUI のテーマとベーススタイルを適用するためのデコレーター。
   */
  decorators: [
    (Story) => (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Story />
      </ThemeProvider>
    ),
  ],
};

export default preview;
