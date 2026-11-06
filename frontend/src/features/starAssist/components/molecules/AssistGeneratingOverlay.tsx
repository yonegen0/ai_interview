/** @file AssistGeneratingOverlay.tsx @description 回答アシスト5モード共通の生成中GIFオーバーレイ。 */
"use client";

import Image from "next/image";
import Modal from "@mui/material/Modal";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import type { AssistMode } from "@/lib/api/schemas/star";
import { assistModes } from "../../model/steps";

const Overlay = styled(Modal)(({ theme }) => ({
  zIndex: theme.zIndex.modal + 1,
  display: "grid",
  placeItems: "center",
  padding: theme.spacing(2),
  "& .MuiBackdrop-root": {
    backgroundColor: alpha(theme.palette.background.default, 0.86),
    backdropFilter: "blur(9px)",
    WebkitBackdropFilter: "blur(9px)",
  },
}));

const Panel = styled("section")(({ theme }) => ({
  position: "relative",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: theme.spacing(1.5),
  width: "min(100%, 540px)",
  maxHeight: "100%",
  overflowY: "auto",
  color: theme.palette.text.primary,
  textAlign: "center",
  outline: "none",
}));

const ModeTag = styled("span")(({ theme }) => ({
  minWidth: 160,
  borderRadius: 999,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.16)}`,
  padding: theme.spacing(0.75, 2),
  background: alpha(theme.palette.background.paper, 0.6),
  ...theme.typography.body2,
  color: theme.palette.text.secondary,
}));

const ThinkingImage = styled(Image)({
  display: "block",
  width: "min(100%, 480px)",
  height: "auto",
  maxHeight: "min(65vh, 480px)",
  objectFit: "contain",
});

const Description = styled("p")(({ theme }) => ({
  ...theme.typography.body1,
  margin: 0,
  lineHeight: 1.75,
  color: theme.palette.text.secondary,
  whiteSpace: "pre-line",
}));

const Heading = styled("h2")(({ theme }) => ({
  ...theme.typography.h5,
  margin: 0,
  fontWeight: 700,
}));

const ScreenReaderHeading = styled("h2")({
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
});

const ReturnButton = styled(Button)(({ theme }) => ({
  color: theme.palette.text.secondary,
}));

export type AssistGeneratingOverlayProps = {
  open: boolean;
  mode: AssistMode;
  onDismiss: () => void;
};

/** 閉じる操作は表示のみを終了し、進行中の生成APIを取り消さない。 */
export function AssistGeneratingOverlay({
  open,
  mode,
  onDismiss,
}: AssistGeneratingOverlayProps) {
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const description = mode === "star"
    ? "入力内容を整理し、面接で伝わる3つの回答案を作成しています"
    : "入力内容を整理し、面接で伝わる回答案を作成しています";

  return (
    <Overlay open={open} onClose={onDismiss} aria-labelledby="assist-generating-title"
      aria-describedby="assist-generating-description">
      <Panel role="dialog" aria-modal="true" tabIndex={-1}>
        <ModeTag>{assistModes[mode].label}</ModeTag>
        {reducedMotion ? (
          <Heading id="assist-generating-title">回答を生成しています</Heading>
        ) : (
          <ScreenReaderHeading id="assist-generating-title">
            回答を生成しています
          </ScreenReaderHeading>
        )}
        <ThinkingImage
          src={reducedMotion
            ? "/images/mascot/mascot-thinking.webp"
            : "/images/mascot/mascot-thinking-animation.gif"}
          alt={reducedMotion ? "回答を考えているマスコット" : "回答生成中のマスコットアニメーション"}
          width={508}
          height={508}
          unoptimized
          priority
        />
        <Description id="assist-generating-description" role="status" aria-live="polite">
          {description}
        </Description>
        <ReturnButton type="button" variant="text" onClick={onDismiss}>
          画面に戻る（生成は継続）
        </ReturnButton>
      </Panel>
    </Overlay>
  );
}
