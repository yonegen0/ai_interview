/** @file PracticeStartTemplate.tsx @description Presentation and composition for PracticeStartTemplate. */
"use client";
import { styled } from "@mui/material/styles";
import { Header } from "@/components/molecules/Header";
import { MascotCharacter } from "@/components/atoms/MascotCharacter";
import {
  PracticeSelector,
  type PracticeSelectorProps,
} from "../organisms/PracticeSelector";
const Introduction = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  alignItems: "center",
  gap: theme.spacing(1.5),
  marginBottom: theme.spacing(3),
  [theme.breakpoints.up("md")]: { gap: theme.spacing(3) },
}));
export const PracticeStartTemplate = (props: PracticeSelectorProps) => (
  <>
    <Introduction>
      <Header
        eyebrow="INTERVIEW PRACTICE"
        title="今日は何を練習しますか？"
        description="通し練習かカテゴリ練習を選べます。難易度は標準です。"
      />
      <MascotCharacter variant="welcome" size="lg" loading="eager" />
    </Introduction>
    <PracticeSelector {...props} />
  </>
);
