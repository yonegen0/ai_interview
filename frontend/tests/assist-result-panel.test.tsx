/** @file assist-result-panel.test.tsx @description 新規生成だけの自動表示、確認キャンセルと反映失敗時の成果物保持。 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { useForm, useWatch } from "react-hook-form";
import { beforeEach, expect, it, vi } from "vitest";
import { StarAssistPanel } from "@/features/starAssist/components/organisms/StarAssistPanel";
import type { StarWorkspace } from "@/features/starAssist/hooks/useStarWorkspace";
import { emptyStarInput, type AssistMode, type StarInput } from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";

const generatedId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const candidates: StarInput["candidates"] = [
  { id: "A", style: "conclusion", text: "案A" },
  { id: "B", style: "action", text: "案B" },
  { id: "C", style: "conversational", text: "案C" },
];
const apply = vi.fn();

vi.mock("@/features/starAssist/components/organisms/StarAssistDialog", () => ({
  StarAssistDialog: ({ open, onGenerationQueued, onAdopt, onViewResult }: {
    open: boolean;
    onGenerationQueued: (id: string) => void;
    onAdopt: () => void;
    onViewResult: () => void;
  }) => open ? (
    <section role="dialog" aria-label="入力画面">
      <button type="button" onClick={() => onGenerationQueued(generatedId)}>新規生成を開始</button>
      <button type="button" onClick={onAdopt}>生成結果を採用する</button>
      <button type="button" onClick={onViewResult}>生成した回答を見る</button>
    </section>
  ) : null,
}));
vi.mock("@/features/starAssist/components/organisms/AssistResultDialog", () => ({
  AssistResultDialog: ({ open, onClose, onBack, onApply }: {
    open: boolean;
    onClose: () => void;
    onBack: () => void;
    onApply: (id: "A" | "B" | "C") => void;
  }) => open ? (
    <section role="dialog" aria-label="成果物">
      <button type="button" onClick={onClose}>成果物を閉じる</button>
      <button type="button" onClick={onBack}>入力画面に戻る</button>
      <button type="button" onClick={() => onApply("B")}>案Bを使う</button>
    </section>
  ) : null,
}));

function Harness({ restored = false, hasAnswer = false, waiting = false }: {
  restored?: boolean;
  hasAnswer?: boolean;
  waiting?: boolean;
}) {
  const form = useForm<StarInput>({
    defaultValues: restored
      ? { ...emptyStarInput(), generationId: generatedId, candidates }
      : emptyStarInput(mode),
  });
  const input = useWatch({ control: form.control }) as StarInput;
  const workspace = {
    input, form, mode, available: true, contextId: null, loading, busy, pending,
    status: "保存済", error: null, migrationWarning: null, savedPreview: null,
    resultWaiting: waiting, generating: false, apply,
    adopt: vi.fn().mockReturnValue(true),
  } as unknown as StarWorkspace;
  return (
    <ThemeProvider theme={theme}>
      <button type="button" data-testid="publish-result" onClick={() => {
        form.setValue("generationId", generatedId, { shouldDirty: true });
        form.setValue("candidates", candidates, { shouldDirty: true });
      }}>モック生成完了</button>
      <StarAssistPanel workspace={workspace} hasAnswer={hasAnswer} />
    </ThemeProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apply.mockResolvedValue(true);
});

it("automatically shows only the newly requested generation once", async () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  fireEvent.click(screen.getByRole("button", { name: "新規生成を開始" }));
  fireEvent.click(screen.getByTestId("publish-result"));
  await waitFor(() => expect(screen.getByRole("dialog", { name: "成果物" })).toBeInTheDocument());
  expect(screen.queryByRole("dialog", { name: "入力画面" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "成果物を閉じる" }));
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  expect(screen.queryByRole("dialog", { name: "成果物" })).not.toBeInTheDocument();
});

it("does not automatically pop up a restored draft", () => {
  render(<Harness restored />);
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  expect(screen.getByRole("dialog", { name: "入力画面" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "成果物" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "生成した回答を見る" }));
  expect(screen.getByRole("dialog", { name: "成果物" })).toBeInTheDocument();
});

it("keeps the result and selected B after cancelling overwrite", async () => {
  render(<Harness restored hasAnswer />);
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  fireEvent.click(screen.getByRole("button", { name: "生成した回答を見る" }));
  fireEvent.click(screen.getByRole("button", { name: "案Bを使う" }));
  expect(screen.getByText("入力中の回答を置き換えますか？"))
    .toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "キャンセル" }));
  await waitFor(() =>
    expect(screen.getByRole("dialog", { name: "成果物" })).toBeInTheDocument(),
  );
  expect(apply).not.toHaveBeenCalled();
});

it("keeps the result open when applying B fails", async () => {
  apply.mockResolvedValue(false);
  render(<Harness restored />);
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  fireEvent.click(screen.getByRole("button", { name: "生成した回答を見る" }));
  fireEvent.click(screen.getByRole("button", { name: "案Bを使う" }));
  await waitFor(() => expect(apply).toHaveBeenCalledWith("B"));
  expect(screen.getByRole("dialog", { name: "成果物" })).toBeInTheDocument();
});

it("offers the independent tutorial only in a safe STAR state and keeps normal dialogs exclusive", () => {
  render(<Harness hasAnswer />);
  const launch = screen.getByRole("button", { name: "使い方を体験する" });
  fireEvent.click(launch);
  expect(screen.getByRole("dialog", { name: "STARアシストの使い方を体験" })).toBeInTheDocument();
  // Clicking the background trigger programmatically must not open a second dialog.
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  expect(screen.queryByRole("dialog", { name: "入力画面" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "チュートリアルを閉じる" }));
  expect(screen.queryByRole("dialog", { name: "STARアシストの使い方を体験" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /エピソード作成アシスト/ }));
  expect(screen.getByRole("dialog", { name: "入力画面" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "使い方を体験する" })).not.toBeInTheDocument();
  expect(apply).not.toHaveBeenCalled();
});

it.each([
  { mode: "prep" as const },
  { busy: true },
  { pending: true },
  { loading: true },
])("hides the tutorial while another mode or operation is active: %o", (props) => {
  render(<Harness {...props} />);
  expect(screen.queryByRole("button", { name: "使い方を体験する" })).not.toBeInTheDocument();
});
