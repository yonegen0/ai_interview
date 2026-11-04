/** @file full-text-dialog.test.tsx @description 長文プレビューと共通全文Dialogの表示・操作。 */
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FullTextDialog } from "@/components/organisms/FullTextDialog";
import { FullTextPreview } from "@/components/organisms/FullTextPreview";

function DialogExample({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>開く</button>
      <FullTextDialog
        open={open}
        onClose={() => setOpen(false)}
        title="初回の回答"
        text={text}
      />
    </>
  );
}

afterEach(() => vi.restoreAllMocks());

it("keeps all text and line breaks, and closes using Escape with focus restoration", async () => {
  const user = userEvent.setup();
  const text = "1行目\n<script>window.evil=true</script>\n3行目";
  render(<DialogExample text={text} />);
  const trigger = screen.getByRole("button", { name: "開く" });
  await user.click(trigger);
  expect(screen.getByRole("heading", { name: "初回の回答（全文）" })).toBeInTheDocument();
  expect(screen.getByRole("dialog").querySelector("p")?.textContent).toBe(text);
  expect(document.querySelector("script")).toBeNull();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("closes by the header close button and by the footer button", async () => {
  const user = userEvent.setup();
  render(<DialogExample text="内容" />);
  await user.click(screen.getByRole("button", { name: "開く" }));
  await user.click(screen.getByRole("button", { name: "ダイアログを閉じる" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: "開く" }));
  await user.click(screen.getByRole("button", { name: "閉じる" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("shows the full-text action only when the preview is actually clipped", async () => {
  const user = userEvent.setup();
  render(<FullTextPreview title="改善ポイント" text="長い本文です。\n続く本文です。" lines={2} />);
  const paragraph = screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "長い本文です。\n続く本文です。");
  expect(screen.queryByRole("button", { name: "改善ポイントの全文を見る" })).not.toBeInTheDocument();
  Object.defineProperty(paragraph, "scrollHeight", { configurable: true, value: 90 });
  Object.defineProperty(paragraph, "clientHeight", { configurable: true, value: 45 });
  fireEvent.resize(window);
  const openButton = await screen.findByRole("button", { name: "改善ポイントの全文を見る" });
  await user.click(openButton);
  expect(screen.getByRole("heading", { name: "改善ポイント（全文）" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "閉じる" }));
  await waitFor(() => expect(openButton).toHaveFocus());
  Object.defineProperty(paragraph, "scrollHeight", { configurable: true, value: 45 });
  fireEvent.resize(window);
  await waitFor(() => expect(screen.queryByRole("button", { name: "改善ポイントの全文を見る" })).not.toBeInTheDocument());
});
