/** @file StarAssistDialog.tsx @description STARアシストの4ステップ入力・生成・結果を示すダイアログ。 */
"use client";

import { useState } from "react";
import { Controller } from "react-hook-form";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Alert, useMediaQuery } from "@mui/material";
import { styled, useTheme } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Select } from "@/components/atoms/Select";
import { Text } from "@/components/atoms/Text";
import { Dialog } from "@/components/organisms/Dialog";
import { STAR_INPUT_LIMIT, OTHER_ASSIST_INPUT_LIMIT, countStarNotes, starInputSchema, starNotesSchema, targetCategories, type StarInput } from "@/lib/api/schemas/star";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";
import { assistModes } from "../../model/steps";
import { StarAssistStepper } from "../molecules/StarAssistStepper";
import { StarAssistTips } from "../molecules/StarAssistTips";
import { StarAssistStepForm } from "../molecules/StarAssistStepForm";
import { StarAssistHeader, StarAssistColumns, StarAssistSettings, StarAssistSettingFields, StarAssistSettingActions } from "../molecules/StarAssistPresentation";
import { AssistGeneratingOverlay } from "../molecules/AssistGeneratingOverlay";

const Content = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  paddingBottom: theme.spacing(1),
}));
const Result = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1),
  padding: theme.spacing(2),
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + theme.palette.divider,
}));
const Footer = styled("div")(({ theme }) => ({
  width: "100%",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: theme.spacing(1),
  padding: theme.spacing(0.5),
  [theme.breakpoints.down("sm")]: {
    flexWrap: "wrap",
    "& .MuiButton-root": { minWidth: 0, paddingInline: theme.spacing(1.25) },
  },
}));
type Props = {
  open: boolean;
  onClose: () => void;
  workspace: StarWorkspace;
  onGenerationQueued: (id: string) => void;
  onAdopt: () => void;
  onViewResult: () => void;
  onDiscard: () => void;
};

export function StarAssistDialog({ open, onClose, workspace: w, onGenerationQueued, onAdopt, onViewResult, onDiscard }: Props) {
  const [step, setStep] = useState(0);
  const [requestingGeneration, setRequestingGeneration] = useState(false);
  const [overlayDismissed, setOverlayDismissed] = useState(false);
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const mode = w.mode;
  const draftMode = w.input.assistType ?? "star";
  const modeChanged = draftMode !== mode;
  const meta = assistModes[mode];
  const steps = meta.steps;
  const last = mode === "follow_up" || step === steps.length - 1;
  const totalCount = countStarNotes(w.input.notes);
  const inputLimit = mode === "star" ? STAR_INPUT_LIMIT : OTHER_ASSIST_INPUT_LIMIT;
  const notesValid = starNotesSchema.safeParse(w.input.notes).success && totalCount <= inputLimit;
  const inputValid = starInputSchema.safeParse(w.input).success;
  const canGenerate = !modeChanged && !w.loading && !w.busy && !w.pending && !w.generating &&
    (mode !== "star" || !!w.input.targetCategory) && notesValid && inputValid &&
    (mode === "follow_up" ? !!w.input.notes.S.trim() &&
      !w.input.notes.T && !w.input.notes.A && !w.input.notes.R :
      steps.some(({ key }) => w.input.notes[key].trim())) &&
    w.quota?.user.remaining !== 0 && w.quota?.global.remaining !== 0;

  const startGenerate = async () => {
    setOverlayDismissed(false);
    setRequestingGeneration(true);
    try {
      const generationId = await w.generate();
      if (generationId) onGenerationQueued(generationId);
    } finally {
      setRequestingGeneration(false);
    }
  };

  const title = <StarAssistHeader mode={mode} onClose={onClose} />;

  const content = (
    <Content>
      <Text role="status" aria-live="polite" variant="caption" color="text.secondary">
        下書き：{w.status}{w.loading ? "（保存版を確認中）" : ""}
      </Text>
      {modeChanged && (
        <Alert severity="warning">
          以前のモードの下書きを保持しています。内容を確認し、明示的に破棄してから新しいモードで生成してください。
        </Alert>
      )}
      {(mode === "star" || mode === "follow_up") && (
        <Text role="status" aria-live="polite" variant="body2"
          color={totalCount > inputLimit ? "error.main" : "text.secondary"}>
          入力文字数：{totalCount} / {inputLimit}文字
        </Text>
      )}
      {totalCount > inputLimit && (
        <Alert severity="error">
          {mode === "star"
            ? "エピソード作成アシストは4項目の合計600文字まで入力できます。内容を短くしてください。"
            : mode === "follow_up" ? "回答のメモは1600文字までです。"
              : "入力は4項目の合計1600文字までです。内容を短くしてください。"}
        </Alert>
      )}
      {mode === "follow_up" ? (
        <StarAssistSettings aria-label="回答のメモ">
          <Controller name="notes.S" control={w.form.control} render={({ field }) => (
            <Input {...field} label="回答のメモ" multiline minRows={6}
              placeholder={"例：送り状を見た\n自分から声をかけた\n3社が新しく利用した"}
              disabled={w.busy || w.pending || modeChanged}
              error={totalCount > inputLimit || !!w.form.formState.errors.notes?.S}
              helperText="思いついたことを箇条書きで入力してください"
            />
          )} />
        </StarAssistSettings>
      ) : (
        <>
          <StarAssistStepper activeStep={step} steps={steps} label={meta.label} />
          <StarAssistColumns>
            <StarAssistStepForm step={step} steps={steps} mode={mode} form={w.form} input={w.input} disabled={false} />
            <StarAssistTips step={step} steps={steps} />
          </StarAssistColumns>
        </>
      )}
      {last && mode === "star" && (
        <StarAssistSettings aria-label="応募先の設定">
          <Text variant="h3" component="h3">応募先の設定</Text>
          <Select
            label="応募先カテゴリ"
            value={w.input.targetCategory ?? ""}
            fullWidth
            disabled={w.busy}
            options={[
              { value: "", label: "選択してください" },
              ...Object.entries(targetCategories).map(([value, label]) => ({ value, label })),
            ]}
            onChange={(value) =>
              w.selectCategory((value || null) as StarInput["targetCategory"])
            }
          />
          <StarAssistSettingFields>
            <Input
              {...w.form.register("industry")}
              label="志望業界（任意）"
              disabled={w.busy}
              error={!!w.form.formState.errors.industry}
              helperText={w.form.formState.errors.industry?.message}
            />
            <Input
              {...w.form.register("company")}
              label="応募先企業名（任意）"
              disabled={w.busy}
              error={!!w.form.formState.errors.company}
              helperText={w.form.formState.errors.company?.message}
            />
          </StarAssistSettingFields>
          <StarAssistSettingActions>
            <Button type="button" size="small" onClick={() => void w.savePreferences(true)}
              disabled={w.busy || w.pending || !w.input.targetCategory}>
              このカテゴリを14日保存
            </Button>
            <Button type="button" size="small" onClick={() => void w.savePreferences()}
              disabled={w.busy || w.pending}>
              業界・企業名を14日保存
            </Button>
          </StarAssistSettingActions>
        </StarAssistSettings>
      )}
      {last && w.quota && (
        <Text variant="body2">
          回答アシスト共通の生成枠：あなた {w.quota.user.remaining} / 全体 {w.quota.global.remaining}（JST {w.quota.month}）
        </Text>
      )}
      {last && (
        <Text variant="body2" color="text.secondary">
          回答アシストの生成は、AI回答チェック・AI面接コーチと共通の月間利用上限にも制限されます。この枠が残っていても生成できない場合があります。
        </Text>
      )}
      {last && w.resultWaiting && (
        <Alert severity="info" action={
          <Button type="button" size="small" onClick={onAdopt}>生成結果を採用する</Button>
        }>
          生成中に編集が進みました。結果で入力を上書きしていません。
        </Alert>
      )}
      {last && mode === "star" && w.generationCategory && (
        <Text variant="body2">現在の3案の生成時カテゴリ：{targetCategories[w.generationCategory]}</Text>
      )}
      {last && w.input.candidates.length > 0 && (
        <Result aria-label="生成した回答アシスト">
          <Text component="h3" variant="h3">
            {mode === "star" ? "生成した3案の回答" : "生成した回答案"}
          </Text>
          <Text variant="body2" color="text.secondary">
            生成済みの回答を確認・編集できます。再表示してもAIを再実行せず、利用枠を消費しません。
          </Text>
          <Button type="button" variant="contained" onClick={onViewResult}
            disabled={modeChanged || w.generating || w.resultWaiting}>
            生成した回答を見る
          </Button>
        </Result>
      )}
      {last && (
        <Button type="button" color="error" size="small" onClick={onDiscard}
          disabled={w.busy || w.pending || w.loading || w.generating}>
          {meta.label}の下書きを破棄
        </Button>
      )}
      {w.error && <Alert severity="error">{w.error}</Alert>}
    </Content>
  );

  const actions = (
    <Footer>
      <Button type="button" variant="outlined" onClick={onClose}>キャンセル</Button>
      <StarAssistSettingActions>
        {mode !== "follow_up" && (
          <Button type="button" variant="outlined" startIcon={<ArrowBackIcon />}
            disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>
            戻る
          </Button>
        )}
        {last ? (
          <Button type="button" variant="contained" endIcon={<AutoAwesomeOutlinedIcon />}
            disabled={!canGenerate}
            onClick={() => void startGenerate()}>
            {w.generating ? "回答を生成しています…" :
              w.input.candidates.length ? "新しい入力で再生成（1回）" :
              mode === "star" ? "3案を生成（1回）" :
              mode === "follow_up" ? "回答例を生成（1案）" : "回答案を生成（1回）"}
          </Button>
        ) : (
          <Button type="button" variant="contained" endIcon={<ArrowForwardIcon />}
            disabled={w.busy}
            onClick={() => setStep((value) => Math.min(steps.length - 1, value + 1))}>
            次へ
          </Button>
        )}
      </StarAssistSettingActions>
    </Footer>
  );

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        title={title}
        content={content}
        actions={actions}
        maxWidth="lg"
        fullScreen={fullScreen}
        scrollContent
      />
      <AssistGeneratingOverlay
        open={open && !overlayDismissed && (requestingGeneration || w.generating)}
        mode={mode}
        onDismiss={() => setOverlayDismissed(true)}
      />
    </>
  );
}
