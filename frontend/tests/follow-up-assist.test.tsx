/** @file follow-up-assist.test.tsx @description 深掘り1欄入力と旧モード下書き保護のMockテスト。 */
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { useForm, useWatch } from "react-hook-form";
import { expect, it, vi } from "vitest";
import { StarAssistDialog } from "@/features/starAssist/components/organisms/StarAssistDialog";
import type { StarWorkspace } from "@/features/starAssist/hooks/useStarWorkspace";
import { emptyStarInput, type AssistMode, type StarInput } from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";

const generate = vi.fn().mockResolvedValue("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
function Harness({ savedMode = "follow_up" }: { savedMode?: AssistMode }) {
  const form = useForm<StarInput>({ mode: "onChange", defaultValues: emptyStarInput(savedMode) });
  const input = useWatch({ control: form.control }) as StarInput;
  const workspace = {
    mode: "follow_up", form, input, status: "保存済", loading: false, busy: false,
    pending: false, generating: false, quota: null, error: null,
    resultWaiting: false, generationCategory: null, generate,
  } as unknown as StarWorkspace;
  return <ThemeProvider theme={theme}>
    <StarAssistDialog open onClose={vi.fn()} workspace={workspace}
      onGenerationQueued={vi.fn()} onAdopt={vi.fn()} onViewResult={vi.fn()}
      onDiscard={vi.fn()} />
  </ThemeProvider>;
}

it("shows a single free-note input without STAR stepper and allows short notes", () => {
  render(<Harness />);
  expect(screen.getByRole("heading", { name: "深掘り回答アシスト" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "回答のメモ" })).toBeInTheDocument();
  expect(screen.queryByText("Situation")).not.toBeInTheDocument();
  expect(screen.queryByRole("stepper")).not.toBeInTheDocument();
  const button = screen.getByRole("button", { name: "回答例を生成（1案）" });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "回答のメモ" }), {
    target: { value: "送り状を見た\n声をかけた\n3社利用" },
  });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  expect(generate).toHaveBeenCalledTimes(1);
});

it("does not silently convert an older four-field draft", () => {
  render(<Harness savedMode="prep" />);
  expect(screen.getByText(/以前のモードの下書きを保持しています/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "回答のメモ" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "回答例を生成（1案）" })).toBeDisabled();
});
