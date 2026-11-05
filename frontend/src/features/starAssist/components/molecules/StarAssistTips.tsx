/** @file StarAssistTips.tsx @description 入力段階に応じたヒントを表示する補助カード。 */
"use client";

import CheckIcon from "@mui/icons-material/Check";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import { alpha, styled } from "@mui/material/styles";
import { Text } from "@/components/atoms/Text";
import { starSteps, type AssistStep } from "../../model/steps";
import type { AssistMode } from "@/lib/api/schemas/star";

const Guide = styled("aside")(({ theme }) => ({
  minWidth: 0,
  borderRadius: theme.shape.borderRadius,
  background: alpha(theme.palette.primary.main, 0.07),
  padding: theme.spacing(3),
  alignSelf: "stretch",
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
const Heading = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  marginBottom: theme.spacing(2),
  color: theme.palette.primary.main,
}));
const Points = styled("ul")(({ theme }) => ({
  margin: 0,
  padding: 0,
  listStyle: "none",
  display: "grid",
  gap: theme.spacing(2),
}));
const Point = styled("li")(({ theme }) => ({
  display: "flex",
  alignItems: "flex-start",
  gap: theme.spacing(1),
  minWidth: 0,
  "& svg": { flexShrink: 0, color: theme.palette.primary.main, marginTop: theme.spacing(0.5) },
}));

export function StarAssistTips({ step, steps = starSteps, mode = "star" }: {
  step: number; steps?: readonly AssistStep[]; mode?: AssistMode;
}) {
  const current = steps[step] ?? steps[0];
  return (
    <Guide aria-label={current.label + "の記入例"}>
      <Heading>
        <TipsAndUpdatesOutlinedIcon aria-hidden="true" />
        <Text variant="h3" component="h3">記入例（参考）</Text>
      </Heading>
      <Points>
        {current.tips.map((tip, index) => (
          <Point key={tip}>
            {mode === "star" ? (
              <CheckIcon fontSize="small" aria-hidden="true" />
            ) : (
              <Text variant="body2" color="primary.main" component="span">
                {["①", "②", "③"][index]}
              </Text>
            )}
            <Text variant="body2">{tip}</Text>
          </Point>
        ))}
      </Points>
      <Text variant="caption" color="text.secondary">
        {mode === "star"
          ? "記入例は入力欄にコピーされません。自分の事実や考えだけを入力してください。"
          : "記入例は3つの異なる回答パターンです。同じ番号を4ステップで参考にできます。すべて入力する必要はありません。自分の経験や考えに置き換えてください。"}
      </Text>
    </Guide>
  );
}
