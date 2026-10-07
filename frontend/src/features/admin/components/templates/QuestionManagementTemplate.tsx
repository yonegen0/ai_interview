/** @file QuestionManagementTemplate.tsx @description Presentation and composition for QuestionManagementTemplate. */
"use client";
import { styled } from "@mui/material/styles";
import { Header } from "@/components/molecules/Header";
import { Text } from "@/components/atoms/Text";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { QuestionEditorList } from "../organisms/QuestionEditorList";
import { QuestionBankStatus } from "../organisms/QuestionBankStatus";
import { QuestionBankConflict } from "../organisms/QuestionBankConflict";
import { QuestionBankPreview } from "../organisms/QuestionBankPreview";
import { QuestionBankSaveConfirmation } from "../organisms/QuestionBankSaveConfirmation";
import type {
  EditorBindings,
  ManagementView,
  ManagementActions,
} from "../../model/editor";
const Editor = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
}));
export type QuestionManagementTemplateProps = {
  view: ManagementView;
  editor: EditorBindings;
  actions: ManagementActions;
};
export function QuestionManagementTemplate({
  view,
  editor,
  actions,
}: QuestionManagementTemplateProps) {
  return (
    <Editor>
      <Header
        title="質問管理"
        description="保存した変更は、新しく開始する練習から反映されます。進行中の練習は元の質問を保持します。"
      />
      <QuestionBankStatus
        loading={view.loading}
        stage={view.stage}
        error={view.error}
        message={view.message}
        onRefresh={actions.refresh}
        onReconfirm={() => void actions.publish()}
      />
      {view.initialized && (
        <>
          <Text>
            {editor.fields.length} / 100問
            {view.changed ? " · 未保存の変更があります" : " · 保存済み"}
          </Text>
          <QuestionBankConflict
            active={view.stage === "conflict"}
            comparison={view.comparison}
            questions={view.questions}
            previousDraft={view.previousDraft}
            onFetchLatest={() => void actions.fetchLatest()}
            onAdoptLatest={actions.adoptLatest}
          />
          <form onSubmit={actions.confirm}>
            <QuestionEditorList
              {...editor}
              disabled={view.disabled}
              onMove={actions.moveQuestion}
              onRemove={actions.removeQuestion}
            />
            <Actions>
              <Button
                variant="outlined"
                color="primary"
                type="button"
                disabled={view.disabled || editor.fields.length >= 100}
                onClick={actions.appendQuestion}
              >
                質問を追加
              </Button>
              <Button
                variant="outlined"
                color="primary"
                type="button"
                onClick={actions.togglePreview}
              >
                プレビュー
              </Button>
              <Button
                variant="outlined"
                color="error"
                type="button"
                disabled={view.disabled || !view.changed}
                onClick={actions.cancel}
              >
                変更を取り消す
              </Button>
              <Button
                variant="contained"
                color="primary"
                type="submit"
                disabled={!view.canConfirm}
              >
                保存内容を確認
              </Button>
            </Actions>
            {view.stage === "confirm" && (
              <QuestionBankSaveConfirmation
                count={editor.fields.length}
                summary={view.summary}
                onPublish={() => void actions.publish()}
                onBack={actions.back}
              />
            )}
          </form>
          {view.preview && <QuestionBankPreview questions={view.questions} />}
        </>
      )}
    </Editor>
  );
}
