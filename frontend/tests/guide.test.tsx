/** @file guide.test.tsx @description 新規ガイドの表示・操作・リンクを重点検証。 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import { afterEach, describe, expect, it } from "vitest";
import { GuideTop } from "@/features/guide/components/GuideTop";
import { GuideBasic } from "@/features/guide/components/GuideBasic";
import { GuideFeatures } from "@/features/guide/components/GuideFeatures";
import { theme } from "@/theme/theme";

const mount = (component: React.ReactElement) =>
  render(<ThemeProvider theme={theme}>{component}</ThemeProvider>);

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

describe("使い方ガイド", () => {
  it("トップから基本・機能別ガイドへ移動できる", () => {
    mount(<GuideTop />);
    expect(screen.getByRole("heading", { name: "基本ガイド" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "機能別ガイド" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /基本ガイドを見る/ })).toHaveAttribute("href", expect.stringMatching(/^\/guide\/basic\/?$/));
    expect(screen.getByRole("link", { name: /機能別ガイドを見る/ })).toHaveAttribute("href", expect.stringMatching(/^\/guide\/features\/?$/));
  });

  it("4ステップを移動し、最初から練習へ進める", async () => {
    const user = userEvent.setup();
    mount(<GuideBasic />);
    expect(screen.getByText(/1 \/ 4/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "練習に進む" })).toHaveAttribute("href", expect.stringMatching(/^\/practice\/quick\/?$/));
    await user.click(screen.getByRole("button", { name: "次へ" }));
    expect(screen.getByText("自分の言葉で回答しよう")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "STEP 4を表示" }));
    expect(screen.getByRole("link", { name: /面接練習を始める/ })).toHaveAttribute("href", expect.stringMatching(/^\/practice\/quick\/?$/));
    await user.click(screen.getByRole("button", { name: "戻る" }));
    expect(screen.getByText("AIのアドバイスを確認しよう")).toBeInTheDocument();
  });

  it("左右スワイプの水平操作だけでページを切り替える", () => {
    mount(<GuideBasic />);
    const slide = screen.getByLabelText("基本ガイドのスライド");
    const area = within(slide).getByText("まずは練習を始めよう").parentElement?.parentElement;
    expect(area).toBeTruthy();
    fireEvent.touchStart(area!, { changedTouches: [{ clientX: 260, clientY: 120 }] });
    fireEvent.touchEnd(area!, { changedTouches: [{ clientX: 70, clientY: 128 }] });
    expect(screen.getByText("自分の言葉で回答しよう")).toBeInTheDocument();
    fireEvent.touchStart(area!, { changedTouches: [{ clientX: 80, clientY: 60 }] });
    fireEvent.touchEnd(area!, { changedTouches: [{ clientX: 85, clientY: 240 }] });
    expect(screen.getByText("自分の言葉で回答しよう")).toBeInTheDocument();
  });

  it("7カテゴリは初期状態で閉じ、回答アシスト6種類を表示する", async () => {
    const user = userEvent.setup();
    mount(<GuideFeatures />);
    const headings = ["練習の始め方", "回答アシスト", "AI採点・評価", "深掘り質問",
      "下書き・再挑戦", "進捗・履歴", "アカウント・FAQ"];
    for (const heading of headings) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    const select = screen.getByRole("button", { name: /02 \/ 07/ });
    expect(select).toHaveAttribute("aria-expanded", "false");
    await user.click(select);
    expect(select).toHaveAttribute("aria-expanded", "true");
    for (const title of ["STAR", "PREP", "志望動機", "転職理由", "キャリアプラン", "深掘り回答"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText(/おすすめ：STAR/)).toBeInTheDocument();
  });

  it("アンカー直リンクで対象カテゴリを開く", () => {
    window.history.replaceState({}, "", "/guide/features/#history");
    mount(<GuideFeatures />);
    const heading = screen.getByText("進捗・履歴");
    const summary = heading.closest("button");
    expect(summary).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("練習履歴・絞り込み")).toBeInTheDocument();
  });
});
