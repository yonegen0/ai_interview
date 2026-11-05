/** @file select-category.test.tsx @description 共通Select互換とカテゴリ装飾の操作回帰を確認する。 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it, vi } from "vitest";
import { Select } from "@/components/atoms/Select";
import { theme } from "@/theme/theme";

const options = [
  { value: "intro", label: "自己紹介", secondaryLabel: "（2問）" },
  { value: "career", label: "長めのカテゴリ名でも表示が保たれる職歴", secondaryLabel: "（10問）" },
] as const;

function mountCategory(value: "intro" | "career" | "" = "intro", disabled = false) {
  const onChange = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <Select
        label="練習するカテゴリ"
        variant="category"
        value={value}
        onChange={onChange}
        options={options}
        disabled={disabled}
        fullWidth
      />
    </ThemeProvider>,
  );
  return onChange;
}

it("shows the selected category and count without menu decoration when closed", () => {
  mountCategory();
  const select = screen.getByRole("combobox", { name: "練習するカテゴリ" });
  expect(select).toHaveTextContent("自己紹介");
  expect(select).toHaveTextContent("（2問）");
  expect(select.querySelector("svg")).toBeNull();
});

it("marks only the selected menu item and changes values through the common Select", () => {
  const onChange = mountCategory();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "練習するカテゴリ" }));
  const listbox = screen.getByRole("listbox");
  const items = within(listbox).getAllByRole("option");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveAttribute("aria-selected", "true");
  expect(items[1]).toHaveAttribute("aria-selected", "false");
  expect(within(items[0]).getByTestId("CheckRoundedIcon")).toBeInTheDocument();
  expect(within(items[1]).queryByTestId("CheckRoundedIcon")).toBeNull();
  expect(items[0]).toHaveTextContent("（2問）");
  expect(items[1]).toHaveTextContent("（10問）");
  fireEvent.click(items[1]);
  expect(onChange).toHaveBeenCalledWith("career");
});

it("preserves the default variant and does not decorate its choices", () => {
  render(
    <ThemeProvider theme={theme}>
      <Select
        label="標準セレクト"
        value="intro"
        onChange={vi.fn()}
        options={[{ value: "intro", label: "自己紹介" }]}
      />
    </ThemeProvider>,
  );
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "標準セレクト" }));
  const option = screen.getByRole("option", { name: "自己紹介" });
  expect(within(option).queryByTestId("CheckRoundedIcon")).toBeNull();
  expect(option).toHaveAttribute("aria-selected", "true");
});

it("keeps the category selection disabled when requested", () => {
  mountCategory("intro", true);
  const select = screen.getByRole("combobox", { name: "練習するカテゴリ" });
  expect(select).toHaveAttribute("aria-disabled", "true");
  fireEvent.mouseDown(select);
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("supports keyboard open and Escape close", () => {
  mountCategory();
  const select = screen.getByRole("combobox", { name: "練習するカテゴリ" });
  select.focus();
  fireEvent.keyDown(select, { key: "ArrowDown" });
  expect(screen.getByRole("listbox")).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
});
