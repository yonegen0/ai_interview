/** @file Link.stories.tsx @description 共通Linkの表示形式、操作、狭幅表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { Link } from "@/components/atoms/Link";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const meta = {
  title: "Components/Atoms/Link",
  component: Link,
  parameters: { layout: "padded" },
  args: {
    href: "/practice/",
    children: "新しい練習を始める",
    onClick: fn(),
  },
} satisfies Meta<typeof Link>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 既存Story IDを維持しつつ、表示名だけを現在のデザインへ合わせる。 */
export const Glass: Story = {
  name: "Underline",
  parameters: {
    docs: {
      description: {
        story: "背景や枠を持たず、通常時から下線で識別できる標準リンク。",
      },
    },
  },
  play: async ({ canvasElement }) => {
    const link = within(canvasElement).getByRole("link", {
      name: "新しい練習を始める",
    });
    await expect(link).toHaveAttribute("href", "/practice/");
  },
};

export const Text: Story = {
  args: {
    href: "/",
    variant: "text",
    children: "Interview Pocket",
  },
};

export const LongLabel: Story = {
  args: {
    children: "送信済みの回答について評価結果を確認し、現在の面接練習へ戻る",
  },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};

export const Mobile: Story = {
  ...LongLabel,
  globals: { viewport: { value: "iphoneSe" } },
};

export const KeyboardNavigation: Story = {
  play: async ({ args, canvasElement }) => {
    const link = within(canvasElement).getByRole("link", {
      name: "新しい練習を始める",
    });
    await userEvent.tab();
    await expect(link).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await expect(args.onClick).toHaveBeenCalledOnce();
  },
};
