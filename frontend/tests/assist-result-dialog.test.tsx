/** @file assist-result-dialog.test.tsx @description 生成成果物の候補切り替え・編集・コピー・5モード表示を確認。 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { useForm, useWatch } from "react-hook-form";
import { beforeEach, expect, it, vi } from "vitest";
import { AssistResultDialog } from "@/features/starAssist/components/organisms/AssistResultDialog";
import type { StarWorkspace } from "@/features/starAssist/hooks/useStarWorkspace";
import {
  emptyStarInput, type AssistMode, type StarInput,
} from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";

const generationId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const starCandidates: StarInput["candidates"] = [
  { id: "A", style: "conclusion", text: "初期の案A" },
  { id: "B", style: "action", text: "初期の案B" },
  { id: "C", style: "conversational", text: "初期の案C" },
];
const apply = vi.fn();
const close = vi.fn();
const back = vi.fn();
const modes: AssistMode[] = ["star", "prep", "motivation", "career_change", "career_plan"];

function Harness({ mode }: { mode: AssistMode }) {
  const form = useForm<StarInput>({
    mode: "onChange",
    defaultValues: {
      ...emptyStarInput(mode),
      generationId,
      candidates: mode === "star" ? starCandidates : [starCandidates[0]],
    },
  });
  const input = useWatch({ control: form.control }) as StarInput;
  const workspace = {
    input, form, mode, busy: false, pending: false, error: null,
  } as StarWorkspace;
  return (
    <ThemeProvider theme={theme}>
      <AssistResultDialog open workspace={workspace} applying={false}
        onClose={close} onBack={back} onApply={apply} />
    </ThemeProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

it("applies the visible B candidate instead of the initially selected A", () => {
  render(<Harness mode="star" />);
  fireEvent.click(screen.getByRole("tab", { name: "B 行動重視" }));
  expect(screen.getByText("初期の案B")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "この回答を使う" }));
  expect(apply).toHaveBeenCalledWith("B");
});

it("retains independent edits when changing candidates and copies the edited answer", async () => {
  render(<Harness mode="star" />);
  fireEvent.click(screen.getByRole("button", { name: "編集する" }));
  fireEvent.change(screen.getByRole("textbox", { name: "案Aの回答を編集" }), {
    target: { value: "編集済みの案A" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "B 行動重視" }));
  expect(screen.getByText("初期の案B")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "A 結論重視" }));
  expect(screen.getByRole("textbox", { name: "案Aの回答を編集" }))
    .toHaveValue("編集済みの案A");
  fireEvent.click(screen.getByRole("button", { name: "コピー" }));
  await waitFor(() =>
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("編集済みの案A"),
  );
});

it("syncs tabs, dots and arrows without network calls", () => {
  render(<Harness mode="star" />);
  expect(screen.getByRole("button", { name: "前の案" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "次の案" }));
  expect(screen.getByRole("tab", { name: "B 行動重視" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("button", { name: "案Cを表示" }));
  expect(screen.getByRole("button", { name: "次の案" })).toBeDisabled();
});

it.each(modes)("renders the correct candidate count for %s", (mode) => {
  render(<Harness mode={mode} />);
  if (mode === "star") {
    expect(screen.getAllByRole("tab")).toHaveLength(3);
  } else {
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "次の案" })).not.toBeInTheDocument();
  }
  expect(screen.getByRole("button", { name: "この回答を使う" })).toBeEnabled();
});
