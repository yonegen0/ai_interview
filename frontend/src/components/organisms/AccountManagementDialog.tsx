/** @file AccountManagementDialog.tsx @description 認証情報の閲覧と既存アカウント操作への導線を提供する。 */
"use client";

import { useEffect, useId, useRef, useState } from "react";
import AccountCircleOutlinedIcon from "@mui/icons-material/AccountCircleOutlined";
import BadgeOutlinedIcon from "@mui/icons-material/BadgeOutlined";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import LogoutRoundedIcon from "@mui/icons-material/LogoutRounded";
import QueryStatsRoundedIcon from "@mui/icons-material/QueryStatsRounded";
import SpaOutlinedIcon from "@mui/icons-material/SpaOutlined";
import { Alert, Avatar, Button as MuiButton, Dialog as MuiDialog, DialogTitle,
  IconButton, Snackbar, Typography } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { scaledRadius } from "@/theme/tokens";

export type AccountManagementDialogProps = {
  open: boolean;
  admin: boolean;
  sub: string | null;
  phase: string;
  onClose: () => void;
  onHistory?: (tab: 0 | 1) => void;
  onLogout: () => void;
  onExited?: () => void;
};

/** 長さの短いIDは一切露出させず、長いIDも両端だけを表示する。 */
export function maskAccountId(sub: string | null): string {
  if (!sub) return "未取得";
  if (sub.length < 10) return "••••••";
  if (sub.length < 16) return sub.slice(0, 2) + "••••••" + sub.slice(-2);
  return sub.slice(0, 4) + "••••••••" + sub.slice(-4);
}

const GlassDialog = styled(MuiDialog)(({ theme }) => ({
  "& .MuiDialog-paper": {
    position: "relative",
    isolation: "isolate",
    width: "calc(100% - 24px)",
    maxWidth: 560,
    margin: theme.spacing(1.5),
    padding: theme.spacing(3, 3.5, 3.5),
    borderRadius: scaledRadius(theme, 1.9),
    border: "1px solid " + alpha(theme.palette.primary.light, 0.32),
    backgroundColor: alpha(theme.palette.background.paper, 0.97),
    boxShadow: "0 24px 72px " + alpha(theme.palette.primary.dark, 0.19),
    overflowX: "hidden",
    overflowY: "auto",
    maxHeight: "calc(100vh - 32px)",
    "@supports (height: 100dvh)": {
      maxHeight: "calc(100dvh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))",
    },
    "@supports (backdrop-filter: blur(1px))": {
      backgroundColor: alpha(theme.palette.background.paper, 0.86),
      backdropFilter: "blur(20px)",
    },
    "&::before, &::after": {
      content: '""',
      position: "absolute",
      zIndex: -1,
      pointerEvents: "none",
      borderRadius: "50%",
      border: "1px solid " + alpha(theme.palette.primary.light, 0.18),
      background: "radial-gradient(circle, " + alpha(theme.palette.primary.light, 0.18) + ", transparent 72%)",
    },
    "&::before": { width: 260, height: 260, top: -165, left: -135 },
    "&::after": { width: 320, height: 320, right: -210, bottom: -185 },
    [theme.breakpoints.down("sm")]: {
      padding: theme.spacing(2.5, 2, 3),
      borderRadius: scaledRadius(theme, 1.75),
    },
    "@media (prefers-reduced-motion: reduce)": { scrollBehavior: "auto" },
  },
}));

const Panel = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2.5),
  minWidth: 0,
}));
const Header = styled("div")(({ theme }) => ({
  position: "relative",
  display: "grid",
  justifyItems: "center",
  gap: theme.spacing(0.75),
  paddingTop: theme.spacing(1),
  textAlign: "center",
}));
const Leaf = styled("span")(({ theme }) => ({
  display: "grid",
  placeItems: "center",
  width: 46,
  height: 46,
  color: theme.palette.primary.dark,
  background: alpha(theme.palette.primary.light, 0.19),
  borderRadius: "50%",
}));
const CloseButton = styled(IconButton)(({ theme }) => ({
  position: "absolute",
  top: 0,
  right: 0,
  width: 44,
  height: 44,
  background: alpha(theme.palette.background.paper, 0.72),
  color: theme.palette.text.secondary,
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.main },
}));
const AccountTitle = styled(DialogTitle)(({ theme }) => ({
  margin: 0,
  padding: 0,
  fontSize: 28,
  fontWeight: 800,
  color: theme.palette.primary.dark,
  [theme.breakpoints.down("sm")]: { fontSize: 24 },
}));
const AccentLine = styled("span")(({ theme }) => ({
  width: 54,
  height: 3,
  borderRadius: 99,
  background: "linear-gradient(90deg, " + theme.palette.primary.light + ", " + theme.palette.primary.dark + ")",
}));
const ProfileCard = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  minWidth: 0,
  padding: theme.spacing(2.5),
  borderRadius: scaledRadius(theme, 1.5),
  background: alpha(theme.palette.background.paper, 0.8),
  border: "1px solid " + alpha(theme.palette.primary.light, 0.24),
  boxShadow: "0 10px 30px " + alpha(theme.palette.primary.dark, 0.08),
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
const IdentityRow = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.75),
  minWidth: 0,
  flexWrap: "wrap",
}));
const IdentityText = styled("div")(({ theme }) => ({
  flex: "1 1 120px",
  minWidth: 0,
  display: "grid",
  gap: theme.spacing(0.25),
}));
const RoleAvatar = styled(Avatar)(({ theme }) => ({
  width: 56,
  height: 56,
  background: alpha(theme.palette.primary.light, 0.2),
  color: theme.palette.primary.dark,
}));
const AuthBadge = styled("span")(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  padding: theme.spacing(0.65, 1.2),
  borderRadius: 99,
  background: alpha(theme.palette.success.light, 0.12),
  color: theme.palette.success.dark,
  fontSize: 12,
  fontWeight: 700,
  whiteSpace: "nowrap",
  '&[data-verified="false"]': {
    background: alpha(theme.palette.text.secondary, 0.1),
    color: theme.palette.text.secondary,
  },
}));
const IdRow = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  minWidth: 0,
  borderTop: "1px solid " + alpha(theme.palette.primary.light, 0.2),
  paddingTop: theme.spacing(1.75),
}));
const IdText = styled("div")(({ theme }) => ({
  minWidth: 0,
  flex: 1,
  display: "grid",
  gap: theme.spacing(0.25),
  overflowWrap: "anywhere",
}));
const Actions = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.25),
}));
const ActionRow = styled(MuiButton)(({ theme }) => ({
  display: "flex",
  justifyContent: "flex-start",
  gap: theme.spacing(1.5),
  width: "100%",
  minWidth: 0,
  minHeight: 62,
  padding: theme.spacing(1, 2),
  borderRadius: scaledRadius(theme, 1.2),
  textTransform: "none",
  textAlign: "left",
  color: theme.palette.text.primary,
  background: alpha(theme.palette.background.paper, 0.92),
  border: "1px solid " + alpha(theme.palette.primary.light, 0.18),
  boxShadow: "0 4px 16px " + alpha(theme.palette.primary.dark, 0.05),
  "&:hover": {
    background: alpha(theme.palette.primary.light, 0.12),
    borderColor: alpha(theme.palette.primary.main, 0.36),
  },
  "&:active": { background: alpha(theme.palette.primary.light, 0.22) },
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.main, outlineOffset: 2 },
  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
}));
const ActionIcon = styled("span")(({ theme }) => ({
  display: "grid",
  flexShrink: 0,
  placeItems: "center",
  width: 42,
  height: 42,
  borderRadius: "50%",
  background: alpha(theme.palette.primary.light, 0.17),
  color: theme.palette.primary.dark,
}));
const ActionLabel = styled("span")(() => ({
  flex: 1,
  minWidth: 0,
  fontWeight: 700,
  fontSize: 15,
}));

export function AccountManagementDialog({
  open, admin, sub, phase, onClose, onHistory, onLogout, onExited,
}: AccountManagementDialogProps) {
  const headingId = useId();
  const [copyResult, setCopyResult] = useState<"success" | "error" | null>(null);
  const ownerRef = useRef(sub);
  useEffect(() => {
    ownerRef.current = sub;
    setCopyResult(null);
  }, [open, sub]);
  const verified = phase === "authenticated";
  const copyId = async () => {
    if (!sub) return;
    const copiedOwner = sub;
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard)
        throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(copiedOwner);
      if (ownerRef.current === copiedOwner) setCopyResult("success");
    } catch {
      if (ownerRef.current === copiedOwner) setCopyResult("error");
    }
  };
  return (
    <>
      <GlassDialog open={open} onClose={onClose} maxWidth={false} fullWidth
        aria-labelledby={headingId} slotProps={{ transition: { onExited } }}>
        <Panel>
          <Header>
            <CloseButton aria-label="アカウント管理を閉じる" onClick={onClose}>
              <CloseRoundedIcon />
            </CloseButton>
            <Leaf><SpaOutlinedIcon fontSize="large" aria-hidden="true" /></Leaf>
            <AccountTitle id={headingId} component="h2">アカウント管理</AccountTitle>
            <AccentLine aria-hidden="true" />
          </Header>
          <ProfileCard aria-label="ユーザー情報">
            <IdentityRow>
              <RoleAvatar><AccountCircleOutlinedIcon fontSize="large" /></RoleAvatar>
              <IdentityText>
                <Typography variant="body1" fontWeight={800}>
                  {admin ? "管理者アカウント" : "ユーザーアカウント"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {admin ? "管理者" : "一般ユーザー"}
                </Typography>
              </IdentityText>
              <AuthBadge data-verified={verified}>
                <CheckCircleRoundedIcon fontSize="inherit" aria-hidden="true" />
                {verified ? "認証済み" : "確認中"}
              </AuthBadge>
            </IdentityRow>
            <IdRow>
              <BadgeOutlinedIcon fontSize="small" color="primary" aria-hidden="true" />
              <IdText>
                <Typography variant="caption" color="text.secondary">ユーザーID</Typography>
                <Typography variant="body2" fontWeight={600}>{maskAccountId(sub)}</Typography>
              </IdText>
              <IconButton aria-label="ユーザーIDをコピー" onClick={() => { void copyId(); }}
                disabled={!sub} size="medium">
                <ContentCopyRoundedIcon fontSize="small" />
              </IconButton>
            </IdRow>
          </ProfileCard>
          <Actions role="group" aria-label="アカウント操作">
            <ActionRow onClick={() => onHistory?.(0)} disabled={!onHistory}>
              <ActionIcon><HistoryRoundedIcon aria-hidden="true" /></ActionIcon>
              <ActionLabel>利用履歴</ActionLabel>
              <ChevronRightRoundedIcon color="action" aria-hidden="true" />
            </ActionRow>
            <ActionRow onClick={() => onHistory?.(1)} disabled={!onHistory}>
              <ActionIcon><QueryStatsRoundedIcon aria-hidden="true" /></ActionIcon>
              <ActionLabel>利用状況</ActionLabel>
              <ChevronRightRoundedIcon color="action" aria-hidden="true" />
            </ActionRow>
            <ActionRow onClick={onLogout}>
              <ActionIcon><LogoutRoundedIcon aria-hidden="true" /></ActionIcon>
              <ActionLabel>ログアウト</ActionLabel>
              <ChevronRightRoundedIcon color="action" aria-hidden="true" />
            </ActionRow>
          </Actions>
        </Panel>
      </GlassDialog>
      <Snackbar open={Boolean(copyResult) && open} autoHideDuration={3000}
        onClose={() => setCopyResult(null)}>
        <Alert severity={copyResult === "error" ? "error" : "success"}
          onClose={() => setCopyResult(null)}>
          {copyResult === "error" ? "ユーザーIDをコピーできませんでした。" : "ユーザーIDをコピーしました。"}
        </Alert>
      </Snackbar>
    </>
  );
}
