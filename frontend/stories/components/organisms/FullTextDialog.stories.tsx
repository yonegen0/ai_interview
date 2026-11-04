/** @file FullTextDialog.stories.tsx @description 共有全文ダイアログの開閉・長文・モバイル表示。 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { FullTextDialog } from "@/components/organisms/FullTextDialog";
import { Button } from "@/components/atoms/Button";
import { storyTexts } from "../../fixtures";

function Preview({ text = storyTexts.text1000 }: { text?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>全文を見る</Button>
      <FullTextDialog
        open={open}
        onClose={() => setOpen(false)}
        title="初回の回答"
        text={text}
      />
    </>
  );
}

const meta = {
  title: "Components/Organisms/FullTextDialog",
  component: FullTextDialog,
  parameters: { layout: "padded" },
  args: {
    open: true,
    onClose: () => {},
    title: "初回の回答",
    text: storyTexts.text1000,
  },
} satisfies Meta<typeof FullTextDialog>;
export default meta;
type Story = StoryObj<typeof meta>;
export const LongContent: Story = { render: () => <Preview /> };
export const Mobile: Story = {
  render: () => <Preview />,
  globals: { viewport: { value: "iphoneSe" } },
};
