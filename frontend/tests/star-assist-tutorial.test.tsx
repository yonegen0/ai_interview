/** @file star-assist-tutorial.test.tsx @description 固定教材・遷移・実データ隔離・UI操作を確認する。 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { describe, expect, it, vi } from "vitest";
import { StarAssistTutorial } from "@/features/starAssist/tutorial/StarAssistTutorial";
import { getTutorialView, TUTORIAL_COMPLETE_STEP } from "@/features/starAssist/tutorial/useStarAssistTutorial";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_CATEGORY, TUTORIAL_EDIT_AFTER,
  TUTORIAL_EDIT_BEFORE, TUTORIAL_EDITED_A, TUTORIAL_NOTES, TUTORIAL_QUESTION,
  TUTORIAL_CANDIDATE_DESCRIPTIONS, TUTORIAL_STEP_DESCRIPTIONS,
} from "@/features/starAssist/tutorial/tutorialData";
import { countStarNotes, countStarText, starCandidateSchema, starResultSchema, targetCategories } from "@/lib/api/schemas/star";
import { theme } from "@/theme/theme";
import { starSteps, assistModes } from "@/features/starAssist/model/steps";

const setup = () => {
  const onClose = vi.fn();
  render(<ThemeProvider theme={theme}><StarAssistTutorial onClose={onClose} /></ThemeProvider>);
  const dialog = screen.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
  const next = () => fireEvent.click(within(dialog).getByRole("button", { name: "次へ" }));
  const back = () => fireEvent.click(within(dialog).getByRole("button", { name: "戻る" }));
  return { dialog, next, back, onClose };
};

describe("STAR tutorial fixed data", () => {
  it("fits source contracts and preserves the exact ordered candidates", () => {
    expect(countStarNotes(TUTORIAL_NOTES)).toBe(195);
    expect(countStarNotes(TUTORIAL_NOTES)).toBeLessThanOrEqual(600);
    expect(TUTORIAL_CATEGORY).toBe("retail_service");
    expect(targetCategories[TUTORIAL_CATEGORY]).toBe("接客・販売・サービス");
    expect(TUTORIAL_CANDIDATES.map(({ id, style }) => [id, style])).toEqual([
      ["A", "conclusion"], ["B", "action"], ["C", "conversational"],
    ]);
    expect(starResultSchema.safeParse({
      status: "ready", candidates: TUTORIAL_CANDIDATES, missingInformation: [],
    }).success).toBe(true);
    for (const candidate of TUTORIAL_CANDIDATES) {
      expect(starCandidateSchema.safeParse(candidate).success).toBe(true);
      expect(countStarText(candidate.text)).toBeLessThanOrEqual(400);
      expect(countStarText(candidate.text)).toBeLessThanOrEqual(600);
    }
    expect(TUTORIAL_CANDIDATES.map((candidate) => countStarText(candidate.text)))
      .toEqual([261, 264, 285]);
    expect(TUTORIAL_CANDIDATES[0].text.split(TUTORIAL_EDIT_BEFORE)).toHaveLength(2);
    expect(TUTORIAL_EDITED_A).toBe(
      TUTORIAL_CANDIDATES[0].text.replace(TUTORIAL_EDIT_BEFORE, TUTORIAL_EDIT_AFTER),
    );
    expect(countStarText(TUTORIAL_EDITED_A)).toBe(263);
    expect(countStarText(TUTORIAL_EDITED_A)).toBeLessThanOrEqual(400);
    expect(getTutorialView(8).selectedCandidate).toBe("B");
    expect(getTutorialView(9).selectedCandidate).toBe("C");
  });

  it("keeps the 12 STAR examples aligned while leaving other assist modes intact", () => {
    expect(starSteps.map(({ key, tips }) => [key, tips.length])).toEqual([
      ["S", 3], ["T", 3], ["A", 3], ["R", 3],
    ]);
    expect(starSteps.map(({ tips }) => [...tips])).toEqual([
      [
        "商品やサービスの案内で、お客様ごとに使用目的や困りごとが異なっていた",
        "日々の業務で、確認漏れによる作業のやり直しが発生していた",
        "複数人で進める業務で、担当者間の認識にずれがあった"
      ],
      [
        "お客様の要望を把握し、相手に合った提案をする必要があった",
        "確認漏れを防ぎ、作業を正確に進める必要があった",
        "担当範囲と期限を明確にし、手戻りを防ぐ必要があった"
      ],
      [
        "使用目的や困りごとを聞き、提案内容と説明の順番を変えた",
        "確認漏れが起きやすい項目を整理し、確認リストを作った",
        "担当者と作業内容や期限を確認し、共有メモにまとめた"
      ],
      [
        "提案後の説明のやり直しが減り、事前の聞き取りの大切さを学んだ",
        "確認漏れが減り、作業手順を見直す大切さを学んだ",
        "確認の行き違いが減り、早めの情報共有の大切さを学んだ"
      ]
    ]);
    expect(starSteps.every(({ tips }) => tips.every((tip) => tip.trim().length > 0))).toBe(true);
    expect([
      assistModes.prep.steps[0].tips[0],
      assistModes.motivation.steps[0].tips[0],
      assistModes.career_change.steps[0].tips[0],
      assistModes.career_plan.steps[0].tips[0],
    ]).toEqual([
      "私の強みは、課題に気づいたら自分から行動できること",
      "相手の困りごとを理解し、解決につなげる仕事がしたい",
      "現在の仕事で〇〇にやりがいを感じ、その仕事を中心に取り組みたいと思った",
      "3年後には、担当業務を一人で進められるようになりたい",
    ]);
  });

  it("reuses descriptions for the three candidate steps", () => {
    expect(TUTORIAL_QUESTION).toBe("あなたの強みは何ですか？具体的な経験を交えて教えてください。");
    expect(TUTORIAL_STEP_DESCRIPTIONS).toHaveLength(12);
    expect(TUTORIAL_STEP_DESCRIPTIONS.slice(6, 9)).toEqual([
      TUTORIAL_CANDIDATE_DESCRIPTIONS.A,
      TUTORIAL_CANDIDATE_DESCRIPTIONS.B,
      TUTORIAL_CANDIDATE_DESCRIPTIONS.C,
    ]);
  });

  it("derives every backward/forward state from the step alone", () => {
    expect(getTutorialView(1).notes).toEqual({ S: "", T: "", A: "", R: "" });
    expect(getTutorialView(2).notes.S).toBe(TUTORIAL_NOTES.S);
    expect(getTutorialView(3).notes).toEqual({ ...TUTORIAL_NOTES, A: "", R: "" });
    expect(getTutorialView(4).notes.R).toBe("");
    expect(getTutorialView(2).highlight).toBe("S");
    expect(getTutorialView(3).highlight).toBe("T");
    expect(getTutorialView(4).highlight).toBe("A");
    expect(getTutorialView(5).highlight).toBe("R");
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
      expect(within(dialog).getByRole("heading", { name: "体験用の質問" })).toBeInTheDocument();
      expect(within(dialog).getByText(TUTORIAL_QUESTION)).toBeInTheDocument();
      expect(within(dialog).getByText("この質問はチュートリアル専用です。実際の練習中の質問や回答は変更されません。")).toBeInTheDocument();
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
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveValue(TUTORIAL_CANDIDATES[0].text);
    next();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveValue(TUTORIAL_EDITED_A);
    expect(within(dialog).getByText("文章の一部分を、自分の言葉に近い表現へ修正しました。")).toBeInTheDocument();
    back();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveValue(TUTORIAL_CANDIDATES[0].text);
    next();
    expect(within(dialog).getByLabelText("編集画面の文章")).toHaveValue(TUTORIAL_EDITED_A);
    expect(TUTORIAL_CANDIDATES[0].text).toContain(TUTORIAL_EDIT_BEFORE);
  });

  it("keeps presentation-only buttons inert and never exposes an editable field", () => {
    const { dialog, next, onClose } = setup();
    for (let i = 0; i < 5; i++) next();
    const notes = within(dialog).getAllByRole("textbox");
    expect(notes).toHaveLength(4);
    notes.forEach((field) => expect(field).toHaveAttribute("readonly"));
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
