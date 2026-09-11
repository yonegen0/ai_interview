/** @file withAppShell.tsx @description 実アプリと同じ画面幅・余白でFeatureの表示を確認する。 */
import type { Decorator } from "@storybook/nextjs-vite";
import { AppShell } from "@/components/templates/AppShell";

export const withAppShell: Decorator = (Story) => (
  <AppShell>
    <Story />
  </AppShell>
);
