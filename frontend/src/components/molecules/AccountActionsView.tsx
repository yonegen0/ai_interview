/** @file AccountActionsView.tsx @description 権限別ナビゲーションとMUIアカウントメニュー。 */
"use client";

import { useState, type MouseEvent } from "react";
import AccountCircleOutlinedIcon from "@mui/icons-material/AccountCircleOutlined";
import KeyboardArrowDownRoundedIcon from "@mui/icons-material/KeyboardArrowDownRounded";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import LogoutRoundedIcon from "@mui/icons-material/LogoutRounded";
import LayersOutlinedIcon from "@mui/icons-material/LayersOutlined";
import {
  Avatar, Divider, IconButton, ListItemIcon, ListItemText, Menu, MenuItem,
  Typography,
} from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { scaledRadius } from "@/theme/tokens";

const Navigation = styled("nav")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { gap: theme.spacing(0.5) },
}));
const AdminLink = styled(Link)(({ theme }) => ({
  display: "inline-flex", alignItems: "center", gap: theme.spacing(1),
  color: theme.palette.primary.dark, whiteSpace: "nowrap",
  fontSize: theme.typography.body2.fontSize,
  [theme.breakpoints.down("sm")]: { fontSize: theme.typography.caption.fontSize },
}));
const AccountTrigger = styled(IconButton)(({ theme }) => ({
  borderRadius: 999, gap: theme.spacing(0.5),
  minWidth: theme.spacing(9), minHeight: theme.spacing(6),
  padding: theme.spacing(1), color: theme.palette.primary.dark,
  background: alpha(theme.palette.primary.light, 0.19),
  "&:hover": { background: alpha(theme.palette.primary.main, 0.15) },
  [theme.breakpoints.down("sm")]: { minWidth: theme.spacing(7) },
}));
const AccountMenu = styled(Menu)(({ theme }) => ({
  "& .MuiPaper-root": {
    minWidth: 250, maxWidth: "calc(100vw - 32px)",
    borderRadius: scaledRadius(theme, 1.3),
    boxShadow: theme.shadows[5],
    padding: theme.spacing(1),
    border: "1px solid " + alpha(theme.palette.primary.main, 0.1),
  },
}));
const RoleHeader = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1.5),
  padding: theme.spacing(1.5, 1, 2),
}));
const RoleAvatar = styled(Avatar)(({ theme }) => ({
  background: alpha(theme.palette.success.light, 0.18),
  color: theme.palette.primary.dark,
}));
const HighlightItem = styled(MenuItem)(({ theme }) => ({
  color: theme.palette.primary.dark,
  borderRadius: theme.shape.borderRadius,
  "&:hover, &.Mui-focusVisible": { background: alpha(theme.palette.success.light, 0.2) },
}));
const MenuAction = styled(MenuItem)(({ theme }) => ({ borderRadius: theme.shape.borderRadius }));

export type AccountActionsViewProps = {
  authenticated: boolean;
  admin?: boolean;
  sub?: string | null;
  phase?: string;
  onLogout: () => void;
  onHistory?: () => void;
  onManage?: () => void;
};

export const AccountActionsView = ({
  authenticated, admin, onLogout, onHistory, onManage,
}: AccountActionsViewProps) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const close = () => setAnchor(null);
  const clickTrigger = (event: MouseEvent<HTMLElement>) =>
    setAnchor((current) => current ? null : event.currentTarget);
  const logout = () => {
    close();
    onLogout();
  };
  return (
    <Navigation aria-label="アカウント">
      {authenticated ? (
        <>
          {admin && (
            <AdminLink href="/admin/questions/" variant="text">
              <LayersOutlinedIcon aria-hidden="true" fontSize="small" />
              質問管理
            </AdminLink>
          )}
          <AccountTrigger
            aria-label="アカウントメニュー"
            aria-haspopup="menu"
            aria-controls={anchor ? "account-menu" : undefined}
            aria-expanded={Boolean(anchor)}
            onClick={clickTrigger}
          >
            <AccountCircleOutlinedIcon />
            <KeyboardArrowDownRoundedIcon fontSize="small" />
          </AccountTrigger>
          <AccountMenu
            id="account-menu"
            anchorEl={anchor}
            open={Boolean(anchor)}
            onClose={close}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
          >
            <RoleHeader>
              <RoleAvatar><AccountCircleOutlinedIcon /></RoleAvatar>
              <div>
                <Typography variant="body1"><strong>{admin ? "管理者" : "一般ユーザー"}</strong></Typography>
                <Typography variant="caption" color="text.secondary">ログイン済み</Typography>
              </div>
            </RoleHeader>
            <Divider />
            <MenuAction onClick={() => { close(); onManage?.(); }}>
              <ListItemIcon><ManageAccountsOutlinedIcon fontSize="small" /></ListItemIcon>
              <ListItemText>アカウント管理</ListItemText>
            </MenuAction>
            {onHistory && (
              <HighlightItem onClick={() => { close(); onHistory(); }}>
                <ListItemIcon><HistoryRoundedIcon color="primary" fontSize="small" /></ListItemIcon>
                <ListItemText>利用履歴</ListItemText>
              </HighlightItem>
            )}
            <Divider />
            <MenuAction onClick={logout}>
              <ListItemIcon><LogoutRoundedIcon fontSize="small" /></ListItemIcon>
              <ListItemText>ログアウト</ListItemText>
            </MenuAction>
          </AccountMenu>
        </>
      ) : (
        <Link href="/login/" variant="text">ログイン</Link>
      )}
    </Navigation>
  );
};
