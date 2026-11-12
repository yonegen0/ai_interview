/** @file star-assist-tutorial.test.tsx @description 固定教材・遷移・実データ隔離・UI操作を確認する。 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { describe, expect, it, vi } from "vitest";
import { StarAssistTutorial } from "@/features/starAssist/tutorial/StarAssistTutorial";
import { getTutorialView, TUTORIAL_COMPLETE_STEP } from "@/features/starAssist/tutorial/useStarAssistTutorial";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_CATEGORY, TUTORIAL_EDIT_AFTER,
  TUTORIAL_EDIT_BEFORE, TUTORIAL_EDITED_A, TUTORIAL_NOTES,
} from "@/features/starAssist/tutorial/tutorialData";
import { countStarNotes, starCandidateSchema, starResultSchema, targetCategories } from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";

const setup = () => {
  const onClose = vi.fn();
  render(<ThemeProvider theme={theme}><StarAssistTutorial onClose={onClose} /></ThemeProvider>);
  const dialog = screen.getByRole("dialog", { name: "STARアシストの使い方を体験" });
  const next = () => fireEvent.click(within(dialog).getByRole("button", { name: "次へ" }));
  const back = () => fireEvent.click(within(dialog).getByRole("button", { name: "戻る" }));
  return { dialog, next, back, onClose };
};

describe("STAR tutorial fixed data", () => {
  it("fits source contracts and preserves the exact ordered candidates", () => {
    expect(countStarNotes(TUTORIAL_NOTES)).toBe(209);
    expect(countStarNotes(TUTORIAL_NOTES)).toBeLessThanOrEqual(600);
    expect(TUTORIAL_CATEGORY).toBe("office_reception");
    expect(targetCategories[TUTORIAL_CATEGORY]).toBe("事務・受付");
    expect(TUTORIAL_CANDIDATES.map(({ id, style }) => [id, style])).toEqual([
      ["A", "conclusion"], ["B", "action"], ["C", "conversational"],
    ]);
    expect(starResultSchema.safeParse({
      status: "ready", candidates: TUTORIAL_CANDIDATES, missingInformation: [],
    }).success).toBe(true);
    for (const candidate of TUTORIAL_CANDIDATES) {
      expect(starCandidateSchema.safeParse(candidate).success).toBe(true);
      expect(Array.from(candidate.text).length).toBeLessThanOrEqual(400);
    }
    expect(TUTORIAL_CANDIDATES.map((candidate) => Array.from(candidate.text).length))
      .toEqual([276, 284, 285]);
    expect(TUTORIAL_CANDIDATES[0].text.split(TUTORIAL_EDIT_BEFORE)).toHaveLength(2);
    expect(TUTORIAL_EDITED_A).toBe(
      TUTORIAL_CANDIDATES[0].text.replace(TUTORIAL_EDIT_BEFORE, TUTORIAL_EDIT_AFTER),
    );
    expect(Array.from(TUTORIAL_EDITED_A).length).toBe(291);
    expect(TUTORIAL_EDITED_A.length).toBeLessThanOrEqual(400);
    expect(getTutorialView(8).selectedCandidate).toBe("B");
    expect(getTutorialView(9).selectedCandidate).toBe("C");
  });

  it("derives every backward/forward state from the step alone", () => {
    expect(getTutorialView(1).notes).toEqual({ S: "", T: "", A: "", R: "" });
    expect(getTutorialView(2).notes.S).toBe(TUTORIAL_NOTES.S);
    expect(getTutorialView(3).notes).toEqual({ ...TUTORIAL_NOTES, A: "", R: "" });
    expect(getTutorialView(4).notes.R).toBe("");
    expect(getTutorialView(5).notes).toEqual(TUTORIAL_NOTES);
    expect(getTutorialView(5).targetCategory).toBeNull();
    expect(getTutorialView(6).targetCategory).toBe(TUTORIAL_CATEGORY);
    expect(getTutorialView(6).candidatesVisible).toBe(false);
    expect(getTutorialView(7).selectedCandidate).toBe("A");
    expect(getTutorialView(8).selectedCandidate).toBe("B");
    expect(getTutorialView(9).selectedCandidate).toBe("C");
    expect(getTutorialView(10).selectedCandidate).toBe("A");
    expect(getTutorialView(10).editing).toBe(false);
    expect(getTutorialView(11).editing).toBe(true);
    expect(getTutorialView(11).edited).toBe(false);
    expect(getTutorialView(12).edited).toBe(true);
    expect(getTutorialView(12).answer).toBe("");
    expect(getTutorialView(13).answer).toBe(TUTORIAL_EDITED_A);
    expect(getTutorialView(TUTORIAL_COMPLETE_STEP + 5)).toEqual(getTutorialView(13));
    expect(getTutorialView(-10)).toEqual(getTutorialView(1));
    expect(getTutorialView(12).selectedCandidate).toBe("A");
    expect(getTutorialView(12).edited).toBe(true);
  });
});

describe("STAR tutorial dialog", () => {
  it("finishes using only Next, never calls fetch, and can start again", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.reject(new Error("No tutorial network access allowed")));
    try {
      const { dialog, next } = setup();
      expect(within(dialog).getAllByText("未入力", { exact: true })).toHaveLength(4);
      for (let step = 1; step <= 12; step++) {
        expect(within(dialog).getByText("STEP " + step + " / 12")).toBeInTheDocument();
        next();
      }
      expect(within(dialog).getByRole("heading", { name: "チュートリアル完了！" })).toBeInTheDocument();
      expect(within(dialog).getByLabelText("体験用回答欄")).toHaveTextContent(TUTORIAL_EDITED_A);
      fireEvent.click(within(dialog).getByRole("button", { name: "もう一度体験する" }));
      expect(within(dialog).getByText("STEP 1 / 12")).toBeInTheDocument();
      expect(within(dialog).queryByLabelText("体験用回答欄")).not.toBeInTheDocument();
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("reverses candidate selection and text editing without mutating the fixed source", () => {
    const { dialog, next, back } = setup();
    for (let i = 0; i < 7; i++) next();
    expect(within(dialog).getByText(/表示中：B案/)).toBeInTheDocument();
    next();
    expect(within(dialog).getByText(/表示中：C案/)).toBeInTheDocument();
    back();
    expect(within(dialog).getByText(/表示中：B案/)).toBeInTheDocument();
    next();
    next();
    expect(within(dialog).getByText(/表示中：A案/)).toBeInTheDocument();
    next();
    expect(within(dialog).getByText("A案の回答を編集（体験用）")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveTextContent(TUTORIAL_CANDIDATES[0].text);
    next();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveTextContent(TUTORIAL_EDITED_A);
    back();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveTextContent(TUTORIAL_CANDIDATES[0].text);
    next();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveTextContent(TUTORIAL_EDITED_A);
    expect(TUTORIAL_CANDIDATES[0].text).toContain(TUTORIAL_EDIT_BEFORE);
  });

  it("keeps presentation-only buttons inert and never exposes an editable field", () => {
    const { dialog, next, onClose } = setup();
    for (let i = 0; i < 5; i++) next();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("tab")).not.toBeInTheDocument();
    const fakeGenerate = within(dialog).getByText("3案を生成（1回）");
    fireEvent.click(fakeGenerate);
    expect(within(dialog).getByText("STEP 6 / 12")).toBeInTheDocument();
    next();
    fireEvent.click(within(dialog).getByText("B 行動重視"));
    expect(within(dialog).getByText(/表示中：A案/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("この回答を使う"));
    expect(within(dialog).getByText("STEP 7 / 12")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "チュートリアルを閉じる" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
