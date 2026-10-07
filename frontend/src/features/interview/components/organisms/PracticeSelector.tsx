/** @file PracticeSelector.tsx @description Presentation and composition for PracticeSelector. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { ErrorView } from "@/components/organisms/ErrorView";
import { PracticeModeSelector } from "../molecules/PracticeModeSelector";
import { PracticeCategorySelector } from "../molecules/PracticeCategorySelector";
import type {
  PracticeStartView,
  PracticeStartActions,
} from "../../model/practiceStart";
export type PracticeSelectorProps = {
  view: PracticeStartView;
  actions: PracticeStartActions;
};
export const PracticeSelector = ({ view, actions }: PracticeSelectorProps) => (
  <Panel>
    <PracticeModeSelector
      mode={view.mode}
      total={view.options?.totalQuestions}
      disabled={view.disabled}
      onSelect={actions.selectMode}
    />
    {view.loading && <Text role="status">練習の選択肢を読み込んでいます…</Text>}
    {view.optionsError && (
      <ErrorView error={view.optionsError} retry={actions.refresh} />
    )}{" "}
    {view.mode === "category" && (
      <PracticeCategorySelector
        categories={view.options?.categories ?? []}
        selected={view.category}
        disabled={view.disabled}
        onSelect={actions.selectCategory}
      />
    )}
    <Actions>
      <Button
        variant="contained"
        color="primary"
        disabled={!view.canStart}
        onClick={() => void actions.start()}
      >
        {view.starting
          ? "練習を準備しています…"
          : view.recovering
            ? "開始結果を再確認"
            : "練習を始める"}
      </Button>
    </Actions>
    {view.error && <ErrorView error={view.error} />}
  </Panel>
);
