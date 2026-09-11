/** @file MascotCoachCard.tsx @description マスコットと見出し・説明・操作を一体にする案内カード。 */
"use client";

import { Children, type ReactNode } from "react";
import { alpha, styled, type Theme } from "@mui/material/styles";
import { Actions } from "@/components/atoms/Actions";
import {
  MascotCharacter,
  type MascotVariant,
} from "@/components/atoms/MascotCharacter";

export type MascotCoachCardProps = {
  variant: MascotVariant;
  heading: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  emphasis?: "standard" | "featured";
  tone?: "neutral" | "attention" | "error";
  className?: string;
};

type CardStyleProps = {
  $tone: NonNullable<MascotCoachCardProps["tone"]>;
  $hasBody: boolean;
  $hasActions: boolean;
};

const toneStyles = {
  neutral: { palette: "primary", backgroundOpacity: 0.06, borderOpacity: 0.14 },
  attention: { palette: "secondary", backgroundOpacity: 0.1, borderOpacity: 0.2 },
  error: { palette: "error", backgroundOpacity: 0.06, borderOpacity: 0.3 },
} as const;

const getAccent = (theme: Theme, tone: CardStyleProps["$tone"]) =>
  theme.palette[toneStyles[tone].palette].main;

const Card = styled("div", {
  shouldForwardProp: (prop) => !String(prop).startsWith("$"),
})<CardStyleProps>(({ theme, $tone, $hasBody, $hasActions }) => {
  const accent = getAccent(theme, $tone);
  const { backgroundOpacity, borderOpacity } = toneStyles[$tone];
  return {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    gridTemplateAreas: [
      '"heading artwork"',
      ...($hasBody ? ['"body body"'] : []),
      ...($hasActions ? ['"actions actions"'] : []),
    ].join(" "),
    alignItems: "start",
    gap: 16,
    minWidth: 0,
    padding: 16,
    borderRadius: 20,
    border: `1px solid ${alpha(accent, borderOpacity)}`,
    backgroundColor: alpha(accent, backgroundOpacity),
    color: theme.palette.text.primary,
    "@media (min-width: 768px)": {
      padding: 24,
      columnGap: 24,
      gridTemplateAreas: [
        '"heading artwork"',
        ...($hasBody ? ['"body artwork"'] : []),
        ...($hasActions ? ['"actions artwork"'] : []),
      ].join(" "),
    },
  };
});

const Heading = styled("div")({
  gridArea: "heading",
  alignSelf: "center",
  minWidth: 0,
  overflowWrap: "anywhere",
  "& > h2": { margin: 0, fontSize: 20, lineHeight: 1.5, textWrap: "balance" },
  "@media (min-width: 768px)": {
    "& > h2": { fontSize: 22 },
  },
});

const Artwork = styled("div", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<Pick<CardStyleProps, "$tone">>(({ theme, $tone }) => ({
  gridArea: "artwork",
  position: "relative",
  isolation: "isolate",
  alignSelf: "center",
  "&::before": {
    content: '""',
    position: "absolute",
    width: "88%",
    height: "88%",
    left: "6%",
    bottom: "2%",
    borderRadius: "50%",
    backgroundColor: alpha(getAccent(theme, $tone), 0.1),
    zIndex: -1,
  },
}));

const Character = styled(MascotCharacter, {
  shouldForwardProp: (prop) => prop !== "$emphasis",
})<{ $emphasis: NonNullable<MascotCoachCardProps["emphasis"]> }>(
  ({ $emphasis }) => ({
    width: $emphasis === "featured" ? 112 : 96,
    height: $emphasis === "featured" ? 112 : 96,
    "@media (min-width: 768px)": {
      width: $emphasis === "featured" ? 176 : 144,
      height: $emphasis === "featured" ? 176 : 144,
    },
  }),
);

const Body = styled("div")({
  gridArea: "body",
  minWidth: 0,
  overflowWrap: "anywhere",
  fontSize: 14,
  lineHeight: 1.8,
  "& p": { margin: 0, whiteSpace: "pre-wrap" },
  "& p + p": { marginTop: 12 },
  "@media (min-width: 768px)": { fontSize: 16 },
});

const CardActions = styled(Actions)({
  gridArea: "actions",
  marginTop: 0,
  minWidth: 0,
  flexDirection: "column",
  alignItems: "stretch",
  "& > button": { width: "100%", minWidth: 0, overflowWrap: "anywhere" },
  "& > a": { alignSelf: "flex-start" },
  "@media (min-width: 768px)": {
    flexDirection: "row",
    alignItems: "center",
    "& > button": { width: "auto" },
    "& > a": { alignSelf: "auto" },
  },
});

/** 各スロットの意味・状態は利用側に任せ、装飾と配置だけを共通化する。 */
export const MascotCoachCard = ({
  variant,
  heading,
  children,
  actions,
  emphasis = "standard",
  tone = "neutral",
  className,
}: MascotCoachCardProps) => {
  const hasBody = Children.toArray(children).length > 0;
  const hasActions = Children.toArray(actions).length > 0;
  return (
    <Card
      className={className}
      $tone={tone}
      $hasBody={hasBody}
      $hasActions={hasActions}
    >
      <Heading>{heading}</Heading>
      <Artwork $tone={tone} aria-hidden="true">
        <Character variant={variant} $emphasis={emphasis} />
      </Artwork>
      {hasBody && <Body>{children}</Body>}
      {hasActions && <CardActions>{actions}</CardActions>}
    </Card>
  );
};
