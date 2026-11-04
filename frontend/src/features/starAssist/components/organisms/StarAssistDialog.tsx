/** @file StarAssistDialog.tsx @description STARアシストの4ステップ入力・生成・結果を示すダイアログ。 */
"use client";

import { useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Alert, FormControlLabel, IconButton, Radio, RadioGroup, useMediaQuery } from "@mui/material";
import { alpha, styled, useTheme } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Select } from "@/components/atoms/Select";
import { Text } from "@/components/atoms/Text";
import { Dialog } from "@/components/organisms/Dialog";
import { starInputSchema, starNotesSchema, targetCategories, type StarInput } from "@/lib/api/schemas/star";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";
import { starSteps } from "../../model/steps";
import { StarCandidateFields } from "../molecules/StarFields";
import { StarAssistStepper } from "../molecules/StarAssistStepper";
import { StarAssistTips } from "../molecules/StarAssistTips";
import { StarAssistStepForm } from "../molecules/StarAssistStepForm";

const Header = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1),
}));
const HeaderRow = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: theme.spacing(1),
}));
const HeaderIcon = styled(AutoAwesomeOutlinedIcon)(({ theme }) => ({
  color: theme.palette.primary.main,
}));
const Tag = styled("span")(({ theme }) => ({
  borderRadius: theme.shape.borderRadius,
  background: alpha(theme.palette.primary.main, 0.09),
  color: theme.palette.primary.dark,
  padding: theme.spacing(0.5, 1.5),
  ...theme.typography.body2,
  fontWeight: 600,
}));
const Close = styled(IconButton)(({ theme }) => ({
  marginLeft: "auto",
  color: theme.palette.text.secondary,
}));
const Content = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  paddingBottom: theme.spacing(1),
}));
const Columns = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)",
  gap: theme.spacing(2),
  alignItems: "stretch",
  [theme.breakpoints.down("md")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
const Settings = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  padding: theme.spacing(2),
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
}));
const SettingFields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
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
const NextActions = styled("div")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: theme.spacing(1),
}));

type Props = {
  open: boolean;
  onClose: () => void;
  workspace: StarWorkspace;
  onApply: () => void;
  onDiscard: () => void;
};

export function StarAssistDialog({ open, onClose, workspace: w, onApply, onDiscard }: Props) {
  const [step, setStep] = useState(0);
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const last = step === starSteps.length - 1;
  const notesValid = starNotesSchema.safeParse(w.input.notes).success;
  const inputValid = starInputSchema.safeParse(w.input).success;
  const canGenerate = !w.loading && !w.busy && !w.pending && !w.generating &&
    !!w.input.targetCategory && notesValid && inputValid &&
    starSteps.some(({ key }) => w.input.notes[key].trim()) &&
    w.quota?.user.remaining !== 0 && w.quota?.global.remaining !== 0;

  const title = (
    <Header>
      <HeaderRow>
        <HeaderIcon fontSize="large" aria-hidden="true" />
        <Text variant="h2" component="h2">STARアシスト</Text>
        <Tag>面接回答をSTARで整理</Tag>
        <Close aria-label="STARアシストを閉じる" onClick={onClose} size="small">
          <CloseIcon />
        </Close>
      </HeaderRow>
      <Text variant="body2" color="text.secondary">
        エピソードを4つのステップで入力すると、面接で使える回答を作成できます。
      </Text>
    </Header>
  );

  const content = (
    <Content>
      <Text role="status" aria-live="polite" variant="caption" color="text.secondary">
        下書き：{w.status}{w.loading ? "（保存版を確認中）" : ""}
      </Text>
      <StarAssistStepper activeStep={step} />
      <Columns>
        <StarAssistStepForm step={step} form={w.form} input={w.input} disabled={false} />
        <StarAssistTips step={step} />
      </Columns>
      {last && (
        <Settings aria-label="応募先の設定">
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
          <SettingFields>
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
          </SettingFields>
          <NextActions>
            <Button type="button" size="small" onClick={() => void w.savePreferences(true)}
              disabled={w.busy || w.pending || !w.input.targetCategory}>
              このカテゴリを14日保存
            </Button>
            <Button type="button" size="small" onClick={() => void w.savePreferences()}
              disabled={w.busy || w.pending}>
              業界・企業名を14日保存
            </Button>
          </NextActions>
        </Settings>
      )}
      {last && w.quota && (
        <Text variant="body2">
          STAR専用の生成枠：あなた {w.quota.user.remaining} / 全体 {w.quota.global.remaining}（JST {w.quota.month}）
        </Text>
      )}
      {last && (
        <Text variant="body2" color="text.secondary">
          有料生成は通常評価・Coachingと共通の月間利用上限にも制限されます。この枠が残っていても生成できない場合があります。
        </Text>
      )}
      {last && w.resultWaiting && (
        <Alert severity="info" action={
          <Button type="button" size="small" onClick={w.adopt}>生成結果を採用する</Button>
        }>
          生成中に編集が進みました。結果で入力を上書きしていません。
        </Alert>
      )}
      {last && w.generationCategory && (
        <Text variant="body2">現在の3案の生成時カテゴリ：{targetCategories[w.generationCategory]}</Text>
      )}
      {last && w.input.candidates.length > 0 && (
        <Result aria-label="生成したSTAR回答">
          <Text component="h3" variant="h3">生成した3案から選択</Text>
          <Text variant="body2" color="text.secondary">
            生成した回答は、ご自身の事実に合うよう確認・編集してください。正式送信するまでは採点されません。
          </Text>
          <StarCandidateFields form={w.form} input={w.input} disabled={false} />
          <RadioGroup
            aria-label="反映する回答案"
            value={w.input.selectedCandidateId ?? ""}
            onChange={(_, value) =>
              w.form.setValue("selectedCandidateId", value as "A" | "B" | "C",
                { shouldDirty: true, shouldValidate: true })
            }
          >
            {w.input.candidates.map((candidate) => (
              <FormControlLabel
                key={candidate.id}
                value={candidate.id}
                control={<Radio />}
                label={"案" + candidate.id + "を選択"}
              />
            ))}
          </RadioGroup>
          <Button
            type="button"
            variant="contained"
            onClick={onApply}
            disabled={!w.input.selectedCandidateId || w.busy || w.pending || !w.form.formState.isValid}
          >
            この回答を反映
          </Button>
        </Result>
      )}
      {last && (
        <Button type="button" color="error" size="small" onClick={onDiscard}
          disabled={w.busy || w.pending || w.loading || w.generating}>
          STAR下書きを破棄
        </Button>
      )}
      {w.error && <Alert severity="error">{w.error}</Alert>}
    </Content>
  );

  const actions = (
    <Footer>
      <Button type="button" variant="outlined" onClick={onClose}>キャンセル</Button>
      <NextActions>
        <Button type="button" variant="outlined" startIcon={<ArrowBackIcon />}
          disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}>
          戻る
        </Button>
        {last ? (
          <Button type="button" variant="contained" endIcon={<AutoAwesomeOutlinedIcon />}
            disabled={!canGenerate}
            onClick={() => void w.generate()}>
            {w.generating ? "3案を生成しています…" :
              w.input.candidates.length ? "新カテゴリ・メモで再生成（1回）" : "3案を生成（1回）"}
          </Button>
        ) : (
          <Button type="button" variant="contained" endIcon={<ArrowForwardIcon />}
            disabled={w.busy || !notesValid}
            onClick={() => setStep((value) => Math.min(starSteps.length - 1, value + 1))}>
            次へ
          </Button>
        )}
      </NextActions>
    </Footer>
  );

  return (
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
  );
}
