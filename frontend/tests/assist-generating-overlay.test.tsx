/** @file assist-generating-overlay.test.tsx @description 回答アシスト共通の生成中オーバーレイを確認。 */
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it, vi } from "vitest";
import { AssistGeneratingOverlay } from "@/features/starAssist/components/molecules/AssistGeneratingOverlay";
import type { AssistMode } from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";

const allModes: AssistMode[] = ["star", "prep", "motivation", "career_change", "career_plan"];
const renderOverlay = (mode: AssistMode, open = true, onDismiss = vi.fn()) =>
  render(
    <ThemeProvider theme={theme}>
      <AssistGeneratingOverlay open={open} mode={mode} onDismiss={onDismiss} />
    </ThemeProvider>,
  );

it.each(allModes)("displays the PR #144 GIF while %s generates", (mode) => {
  renderOverlay(mode);
  const gif = screen.getByRole("img", { name: /回答生成中のマスコットアニメーション/ });
  expect(gif).toHaveAttribute("src", "/images/mascot/mascot-thinking-animation.gif");
  expect(screen.getByText(/入力内容を整理し/)).toBeInTheDocument();
});

it("keeps ongoing generation independent of dismissing the overlay", () => {
  const onDismiss = vi.fn();
  renderOverlay("star", true, onDismiss);
  fireEvent.click(screen.getByRole("button", { name: "画面に戻る（生成は継続）" }));
  expect(onDismiss).toHaveBeenCalledOnce();
});

it("does not show the overlay when generation is not active", () => {
  renderOverlay("star", false);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
