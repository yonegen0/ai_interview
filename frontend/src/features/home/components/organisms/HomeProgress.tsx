/** @file HomeProgress.tsx @description 進捗カード。回答・採点処理は変更しない。 */
"use client";

import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import TrackChangesRoundedIcon from "@mui/icons-material/TrackChangesRounded";
import { Box, Button, LinearProgress, Typography } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { useHomeProgress } from "../../hooks/useHomeProgress";

const Surface = styled("section")(({ theme }) => ({
  padding: theme.spacing(2.5),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.28)}`,
  borderRadius: theme.shape.borderRadius,
  backgroundColor: theme.palette.background.paper,
  boxShadow: theme.shadows[2],
  minWidth: 0,
  [theme.breakpoints.up("sm")]: { padding: theme.spacing(3.5) },
}));

const Action = styled(Link)(({ theme }) => ({
  width: "100%",
  maxWidth: "none",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  gap: theme.spacing(1),
  minHeight: 54,
  marginTop: theme.spacing(2),
  padding: theme.spacing(1.5),
  backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText,
  borderRadius: theme.shape.borderRadius,
  textDecoration: "none",
  "&:visited": { color: theme.palette.primary.contrastText },
  "&:hover, &:focus-visible": {
    backgroundColor: theme.palette.primary.dark,
    color: theme.palette.primary.contrastText,
    textDecoration: "none",
  },
}));

export function progressMessage(completed: number, total: number) {
  if (total === 0) return "現在、練習できる質問がありません。";
  if (completed === total) return `全${total}問達成！お疲れさまでした！`;
  if (completed === 0) return "最初の1問から始めてみましょう！";
  const fraction = completed / total;
  if (fraction < 1 / 3) return "いいスタートです。その調子！";
  if (fraction < 2 / 3) return "ここまで順調です！";
  return "あと少し！全問達成まで目前です。";
}

export function HomeProgress() {
  const progress = useHomeProgress();
  const { state, authenticated, data } = progress;
  const restoring = state.phase === "restoring" ||
    (state.phase === "refreshing" && !state.sub) ||
    state.phase === "temporarily_unavailable";
  const total = data?.totalQuestions ?? 0;
  const completed = data?.completedQuestions ?? 0;
  const remaining = total - completed;
  const complete = total > 0 && remaining === 0;
  const percent = total > 0 ? (completed / total) * 100 : 0;
  const steps = total <= 8
    ? Array.from({ length: total }, (_, i) => i + 1)
    : Array.from(new Set([
        1, 2, 3,
        ...Array.from({ length: 5 }, (_, i) => Math.max(1, completed - 4 + i)),
        total,
      ])).filter((n) => n <= total).sort((a, b) => a - b);

  return (
    <Surface aria-labelledby="home-progress-title">
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
        <Box sx={(theme) => ({
          display: "grid", placeItems: "center", flexShrink: 0,
          width: 48, height: 48, borderRadius: 2.5,
          bgcolor: alpha(theme.palette.primary.main, 0.09),
          color: "primary.dark",
        })}>
          <TrackChangesRoundedIcon aria-hidden="true" fontSize="large" />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography id="home-progress-title" component="h2" variant="h6"
            sx={{ color: "primary.dark", fontWeight: 800, lineHeight: 1.3 }}>
            面接練習の進捗
          </Typography>
          {data && <Typography variant="body2" sx={{ mt: 0.4 }}>
            {progressMessage(completed, total)}
          </Typography>}
        </Box>
      </Box>

      {restoring || (authenticated && progress.isPending) ? (
        <Typography role="status" sx={{ mt: 2.5 }}>進捗を確認しています…</Typography>
      ) : !authenticated ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2">ログインすると練習の進捗を確認できます。</Typography>
          <Action href="/login/?returnTo=%2F" variant="text">
            ログインして始める <ArrowForwardRoundedIcon aria-hidden="true" />
          </Action>
        </Box>
      ) : progress.isError && !data ? (
        <Box sx={{ mt: 2 }} role="alert">
          <Typography>進捗を読み込めませんでした。</Typography>
          <Button sx={{ mt: 1 }} variant="outlined" onClick={() => void progress.refetch()}>
            再試行
          </Button>
        </Box>
      ) : data ? (
        <Box sx={{ mt: 2.5 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap" }}>
            <Typography sx={{ fontSize: "clamp(1.65rem, 5vw, 2.1rem)", fontWeight: 800 }}>
              {completed} / {total}
              <Typography component="span" sx={{ ml: 0.75, fontSize: "0.95rem", color: "primary.dark" }}>
                問完了
              </Typography>
            </Typography>
            {total > 0 && <Typography sx={(theme) => ({
              px: 1.75, py: 0.4, borderRadius: 10,
              bgcolor: alpha(theme.palette.primary.main, 0.09),
              color: "primary.dark", fontWeight: 700, fontSize: "0.875rem",
            })}>
              {complete ? "全問達成" : `あと${remaining}問`}
            </Typography>}
          </Box>
          {total > 0 && <>
            <LinearProgress variant="determinate" value={percent}
              aria-label="面接練習の完了率" aria-valuetext={`${completed}問 / ${total}問完了`}
              sx={(theme) => ({
                mt: 1.75, height: 10, borderRadius: 10,
                bgcolor: alpha(theme.palette.primary.main, 0.13),
                "& .MuiLinearProgress-bar": {
                  borderRadius: 10,
                  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
                },
              })} />
            <Box aria-hidden="true" sx={{ display: "flex", gap: 0.7, mt: 2, alignItems: "center", justifyContent: "space-between" }}>
              {steps.map((step, index) => (
                <Box key={step} sx={{ display: "flex", alignItems: "center", gap: 0.7, minWidth: 0 }}>
                  {index > 0 && step > steps[index - 1] + 1 && (
                    <Typography sx={{ color: "text.secondary", fontWeight: 700 }}>…</Typography>
                  )}
                  <Box sx={(theme) => ({
                    width: 30, height: 30, flexShrink: 0,
                    display: "grid", placeItems: "center", borderRadius: "50%",
                    fontSize: "0.85rem", fontWeight: 700,
                    bgcolor: step <= completed ? theme.palette.primary.main : alpha(theme.palette.primary.main, 0.1),
                    color: step <= completed ? theme.palette.primary.contrastText : theme.palette.primary.dark,
                  })}>
                    {step <= completed ? <CheckRoundedIcon fontSize="small" /> : step}
                  </Box>
                </Box>
              ))}
            </Box>
            <Typography sx={{ mt: 2, color: "text.secondary", fontSize: "0.9rem", lineHeight: 1.65 }}>
              {complete
                ? "すべての質問を練習しました！これからも繰り返し練習して、自信を磨いていきましょう。"
                : completed === 0
                  ? "まずは1問、練習してみましょう。"
                  : `全問達成まで、あと${remaining}問！少しずつ続けることが自信につながります。`}
            </Typography>
            <Action href={complete ? "/practice/category/" : "/practice/quick/"} variant="text">
              {complete ? "もう一度練習する" : "練習を続ける"}
              <ArrowForwardRoundedIcon aria-hidden="true" />
            </Action>
          </>}
        </Box>
      ) : null}
    </Surface>
  );
}
