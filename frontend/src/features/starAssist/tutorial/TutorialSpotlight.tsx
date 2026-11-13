/** @file TutorialSpotlight.tsx @description 既存Dialog内の対象を暗転から切り抜き、スクロール可能な吹き出しで案内する。 */
"use client";

import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { LinearProgress } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { TUTORIAL_STEP_COUNT } from "./useStarAssistTutorial";
import { TUTORIAL_STEP_TITLES } from "./tutorialData";

export const TUTORIAL_ANCHORS = [
  "star-s", "star-s", "star-t", "star-a", "star-r", "target-category",
  "candidate-a", "candidate-b", "candidate-c", "candidate-a",
  "candidate-edit", "edit-comparison",
] as const;

type Rect = { left: number; top: number; width: number; height: number };
type Placement = "below" | "above" | "compact";
type Geometry = {
  step: number;
  width: number;
  height: number;
  hole: Rect | null;
  placement: Placement;
  popoverLeft: number;
  popoverTop: number;
  popoverWidth: number;
};

const Layer = styled("div")({
  position: "absolute", inset: 0, zIndex: 10, pointerEvents: "none",
});
const Shade = styled("div")(({ theme }) => ({
  position: "absolute", backgroundColor: alpha(theme.palette.common.black, 0.5),
  pointerEvents: "none",
}));
const Outline = styled("div")(({ theme }) => ({
  position: "absolute", boxSizing: "border-box", borderRadius: 14,
  border: "2px solid " + theme.palette.primary.main,
  boxShadow: "0 0 0 2px " + alpha(theme.palette.primary.light, 0.24),
  pointerEvents: "none",
  transition: "opacity 180ms ease",
  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
}));
const Guide = styled("section")(({ theme }) => ({
  position: "absolute", display: "flex", flexDirection: "column",
  gap: theme.spacing(1), boxSizing: "border-box", maxHeight: "min(50dvh, 315px)",
  minWidth: 0, padding: theme.spacing(2), borderRadius: 18,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.4),
  backgroundColor: theme.palette.background.paper,
  color: theme.palette.text.primary,
  boxShadow: theme.shadows[8], pointerEvents: "auto",
  transition: "opacity 180ms ease",
  "&[data-placement='compact']": {
    left: 12, right: 12, bottom: "max(12px, env(safe-area-inset-bottom))",
    width: "auto", maxHeight: "min(52dvh, 300px)",
  },
  "&[data-placement='below']::before, &[data-placement='above']::before": {
    content: '""', position: "absolute", left: "calc(50% - 7px)",
    width: 14, height: 14, backgroundColor: theme.palette.background.paper,
    transform: "rotate(45deg)", border: "1px solid " + alpha(theme.palette.primary.main, 0.4),
  },
  "&[data-placement='below']::before": {
    top: -8, borderRight: 0, borderBottom: 0,
  },
  "&[data-placement='above']::before": {
    bottom: -8, borderLeft: 0, borderTop: 0,
  },
  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
}));
const ProgressHeading = styled("div")({
  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
});
const Message = styled("div")({
  overflowY: "auto", overscrollBehavior: "contain", minHeight: 0,
  overflowWrap: "anywhere",
});
const Controls = styled("div")(({ theme }) => ({
  display: "flex", gap: theme.spacing(1), flexShrink: 0,
  "& .MuiButton-root": {
    minHeight: 44, minWidth: 0, flex: "1 1 0", paddingInline: theme.spacing(1),
  },
}));

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function sameGeometry(a: Geometry | null, b: Geometry) {
  return a !== null && a.step === b.step && a.width === b.width &&
    a.height === b.height && a.placement === b.placement &&
    a.popoverLeft === b.popoverLeft && a.popoverTop === b.popoverTop &&
    a.popoverWidth === b.popoverWidth &&
    JSON.stringify(a.hole) === JSON.stringify(b.hole);
}

function measure(content: HTMLElement, guide: HTMLElement | null, step: number): Geometry | null {
  const paper = content.closest<HTMLElement>(".MuiDialog-paper");
  if (!paper) return null;
  const p = paper.getBoundingClientRect();
  const c = content.getBoundingClientRect();
  const vv = window.visualViewport;
  const visible = {
    left: vv?.offsetLeft ?? 0,
    top: vv?.offsetTop ?? 0,
    right: (vv?.offsetLeft ?? 0) + (vv?.width ?? window.innerWidth),
    bottom: (vv?.offsetTop ?? 0) + (vv?.height ?? window.innerHeight),
  };
  const width = p.width;
  const height = p.height;
  const popoverWidth = Math.min(344, Math.max(0, width - 24));
  const base: Geometry = {
    step, width, height, hole: null, placement: "compact",
    popoverLeft: 12, popoverTop: 0, popoverWidth,
  };
  const anchor = TUTORIAL_ANCHORS[step - 1];
  const target = content.querySelector<HTMLElement>(`[data-tutorial-anchor="${anchor}"]`);
  if (!target) return base;
  const t = target.getBoundingClientRect();
  // The spotlight must be within the actually visible content and visual viewport.
  const left = Math.max(t.left - 6, c.left, p.left, visible.left);
  const top = Math.max(t.top - 6, c.top, p.top, visible.top);
  const right = Math.min(t.right + 6, c.right, p.right, visible.right);
  const bottom = Math.min(t.bottom + 6, c.bottom, p.bottom, visible.bottom);
  if (![left, top, right, bottom].every(Number.isFinite) ||
    right - left < 12 || bottom - top < 12) return base;
  const hole = {
    left: left - p.left, top: top - p.top,
    width: right - left, height: bottom - top,
  };
  const guideHeight = Math.max(190, guide?.offsetHeight ?? 220);
  const lowerRoom = Math.min(c.bottom, visible.bottom, p.bottom) - bottom;
  const upperRoom = top - Math.max(c.top, visible.top, p.top);
  const placement: Placement = lowerRoom >= guideHeight + 16 ? "below"
    : upperRoom >= guideHeight + 16 ? "above" : "compact";
  const popoverLeft = clamp((left + right) / 2 - p.left - popoverWidth / 2,
    12, width - popoverWidth - 12);
  const popoverTop = placement === "below"
    ? bottom - p.top + 12 : top - p.top - guideHeight - 12;
  return { ...base, hole, placement, popoverLeft, popoverTop };
}

export function TutorialSpotlight({
  contentRef, step, description, onNext, onBack, onClose,
}: {
  contentRef: RefObject<HTMLDivElement | null>;
  step: number; description: string;
  onNext: () => void; onBack: () => void; onClose: () => void;
}) {
  const guideRef = useRef<HTMLElement>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const update = useCallback(() => {
    const content = contentRef.current;
    if (!content) return;
    const measured = measure(content, guideRef.current, step);
    if (measured) setGeometry((previous) => sameGeometry(previous, measured) ? previous : measured);
  }, [contentRef, step]);

  useLayoutEffect(() => {
    const content = contentRef.current;
    const paper = content?.closest<HTMLElement>(".MuiDialog-paper");
    if (!content || !paper) return;
    let frame = 0;
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        update();
      });
    };
    const anchor = TUTORIAL_ANCHORS[step - 1];
    const target = content.querySelector<HTMLElement>(`[data-tutorial-anchor="${anchor}"]`);
    // Only a step transition can cause automatic scroll. Scrolling itself only recalculates.
    if (target) {
      const c = content.getBoundingClientRect();
      const t = target.getBoundingClientRect();
      if (t.top > c.bottom - 36 || t.bottom < c.top + 36 || t.top < c.top + 8) {
        content.scrollTop += t.top - c.top - 12;
      }
    }
    schedule();
    const observer = new ResizeObserver(schedule);
    observer.observe(content);
    observer.observe(paper);
    if (target) observer.observe(target);
    content.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      content.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
    };
  }, [contentRef, step, update]);

  const current = geometry?.step === step ? geometry : null;
  const hole = current?.hole ?? null;
  const width = current?.width ?? 0;
  const height = current?.height ?? 0;
  const placement = hole ? current?.placement ?? "compact" : "compact";
  const shade = (style: React.CSSProperties, key: string) =>
    <Shade key={key} data-tutorial-shade={key} style={style} aria-hidden="true" />;

  return (
    <Layer data-testid="tutorial-spotlight" aria-label="チュートリアル案内">
      {hole && width > 0 && height > 0 ? (
        <>
          {shade({ left: 0, top: 0, width, height: hole.top }, "top")}
          {shade({ left: 0, top: hole.top, width: hole.left, height: hole.height }, "left")}
          {shade({ left: hole.left + hole.width, top: hole.top,
            width: Math.max(0, width - hole.left - hole.width), height: hole.height }, "right")}
          {shade({ left: 0, top: hole.top + hole.height, width,
            height: Math.max(0, height - hole.top - hole.height) }, "bottom")}
          <Outline data-testid="tutorial-highlight" data-tutorial-step={step}
            aria-hidden="true" style={hole} />
        </>
      ) : <Shade aria-hidden="true" data-tutorial-shade="fallback"
        style={{ inset: 0 }} />}
      <Guide ref={guideRef} data-testid="tutorial-guide" data-placement={placement}
        style={placement === "compact" ? undefined : {
          left: current?.popoverLeft ?? 12, top: current?.popoverTop ?? 12,
          width: current?.popoverWidth ?? 320,
        }}>
        <ProgressHeading>
          <Text variant="caption" color="text.secondary">STEP {step} / {TUTORIAL_STEP_COUNT}</Text>
          <Text variant="caption" color="text.secondary">体験用・保存されません</Text>
        </ProgressHeading>
        <LinearProgress variant="determinate"
          value={(step - 1) / TUTORIAL_STEP_COUNT * 100}
          aria-label="チュートリアルの進捗"
          sx={{ height: 3, borderRadius: 2 }} />
        <Message id="star-tutorial-description" role="status" aria-live="polite" aria-atomic="true">
          <Text component="h3" variant="subtitle1">{TUTORIAL_STEP_TITLES[step - 1]}</Text>
          <Text variant="body2">{description}</Text>
        </Message>
        <Controls>
          <Button type="button" variant="outlined" disabled={step === 1} onClick={onBack}>
            戻る
          </Button>
          <Button type="button" variant="contained" onClick={onNext}>次へ</Button>
          <Button type="button" variant="text" onClick={onClose}>終了</Button>
        </Controls>
      </Guide>
    </Layer>
  );
}
