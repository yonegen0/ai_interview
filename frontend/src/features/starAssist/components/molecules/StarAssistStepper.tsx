/** @file StarAssistStepper.tsx @description 4つのSTAR入力ステップと進捗表示。 */
"use client";

import { Step, StepLabel, Stepper } from "@mui/material";
import { styled } from "@mui/material/styles";
import { Text } from "@/components/atoms/Text";
import { starSteps } from "../../model/steps";

const Progress = styled(Stepper)(({ theme }) => ({
  padding: theme.spacing(2, 0, 3),
  "& .MuiStepLabel-label": {
    marginTop: theme.spacing(1),
    color: theme.palette.text.secondary,
    whiteSpace: "normal",
  },
  "& .MuiStepLabel-label.Mui-active, & .MuiStepLabel-label.Mui-completed": {
    color: theme.palette.primary.main,
  },
  "& .MuiStepIcon-root.Mui-active, & .MuiStepIcon-root.Mui-completed": {
    color: theme.palette.primary.main,
  },
  [theme.breakpoints.down("sm")]: {
    padding: theme.spacing(1.5, 0, 2),
    "& .MuiStep-root": { paddingInline: theme.spacing(0.25), minWidth: 0 },
    "& .MuiStepIcon-root": { fontSize: theme.spacing(3.5) },
    "& .MuiStepLabel-label": { marginTop: theme.spacing(0.5) },
  },
}));

const StepName = styled("span")(({ theme }) => ({
  display: "grid",
  justifyItems: "center",
  gap: theme.spacing(0.25),
  overflowWrap: "anywhere",
  [theme.breakpoints.down("sm")]: {
    "& .MuiTypography-caption": { fontSize: theme.typography.overline.fontSize },
  },
}));

export function StarAssistStepper({ activeStep }: { activeStep: number }) {
  return (
    <Progress activeStep={activeStep} alternativeLabel aria-label="STARの入力ステップ">
      {starSteps.map((step) => (
        <Step key={step.key}>
          <StepLabel>
            <StepName>
              <Text component="span" variant="body2"><strong>{step.label}</strong></Text>
              <Text component="span" variant="caption" color="text.secondary">
                {step.english}
              </Text>
            </StepName>
          </StepLabel>
        </Step>
      ))}
    </Progress>
  );
}
