/**
 * @file FullTextPreview.tsx
 * @description 行数で省略されたテキストと全文ダイアログへの導線を提供する共通UI。
 */
"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { FullTextDialog } from "./FullTextDialog";

export type FullTextPreviewProps = {
  title: string;
  text: string;
  lines?: 2 | 3;
  icon?: ReactNode;
};

const PreviewLayout = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  minWidth: 0,
  [theme.breakpoints.down("sm")]: {
    flexDirection: "column",
    alignItems: "stretch",
    gap: theme.spacing(1),
  },
}));

const PreviewText = styled("p", {
  shouldForwardProp: (prop) => prop !== "$lines",
})<{ $lines: number }>(({ theme, $lines }) => ({
  ...theme.typography.body1,
  flex: "1 1 auto",
  minWidth: 0,
  width: "100%",
  margin: 0,
  lineHeight: 1.8,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  display: "-webkit-box",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: $lines,
  overflow: "hidden",
}));

const MoreButton = styled(Button)(({ theme }) => ({
  flexShrink: 0,
  whiteSpace: "nowrap",
  minWidth: "auto",
  padding: theme.spacing(0.5, 1.5),
  borderRadius: theme.shape.borderRadius,
  [theme.breakpoints.down("sm")]: {
    alignSelf: "flex-end",
  },
}));

/** 実際に行数を超えた場合に限り「全文を見る」を表示する。 */
export function FullTextPreview({
  title,
  text,
  lines = 3,
  icon,
}: FullTextPreviewProps) {
  const [open, setOpen] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const previewRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const element = previewRef.current;
    if (!element) return;

    const measure = () => {
      setTruncated(element.scrollHeight > element.clientHeight + 1);
    };

    measure();
    window.addEventListener("resize", measure);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    observer?.observe(element);

    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [lines, text]);

  return (
    <>
      <PreviewLayout>
        <PreviewText ref={previewRef} $lines={lines}>
          {text}
        </PreviewText>
        {truncated && (
          <MoreButton
            variant="outlined"
            color="primary"
            size="small"
            onClick={() => setOpen(true)}
            aria-label={title + "の全文を見る"}
          >
            全文を見る
          </MoreButton>
        )}
      </PreviewLayout>
      <FullTextDialog
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        text={text}
        icon={icon}
      />
    </>
  );
}
