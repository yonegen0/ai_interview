/** @file AdminUserManagement.tsx @description Read-only owner-scoped ADMIN history and Cognito nickname management. */
"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Alert, Button, CircularProgress, FormControl, InputLabel, MenuItem, Select,
  TextField, Typography,
} from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthSession } from "@/hooks/useAuthSession";
import { NicknameEditor } from "@/components/organisms/NicknameEditor";
import { Dialog } from "@/components/organisms/Dialog";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
import { HistoryList, assistLabels, formatHistoryDate, historyStatus } from "@/features/history/components/HistoryList";
import { getAdminUsers, getAdminUserFeedback, putAdminNickname } from "@/lib/api/adminUsers";
import type { AdminUser } from "@/lib/api/schemas/adminUsers";
import type { HistoryItem, HistoryMode, HistoryPeriod } from "@/lib/api/schemas/history";
import { useAdminUserHistory } from "../../hooks/useAdminUserHistory";

const Layout = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2.5), minWidth: 0,
}));
const Card = styled("section")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1.5), minWidth: 0,
  padding: theme.spacing(2.5),
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.17),
  background: theme.palette.background.paper,
  boxShadow: "0 8px 24px " + alpha(theme.palette.primary.dark, 0.06),
  overflowWrap: "anywhere",
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
const UserGrid = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 300px), 1fr))",
  gap: theme.spacing(1.5), minWidth: 0,
}));
const Controls = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", gap: theme.spacing(1),
  "& button": { minHeight: 44 },
}));
const Filters = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.spacing(1.5),
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
const Stats = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))",
  gap: theme.spacing(1),
}));
const Stat = styled("div")(({ theme }) => ({
  minWidth: 0, padding: theme.spacing(1.5),
  background: alpha(theme.palette.primary.main, 0.055),
  borderRadius: theme.shape.borderRadius, display: "grid", gap: theme.spacing(0.5),
}));
const LongText = styled(Typography)({ overflowWrap: "anywhere", minWidth: 0, whiteSpace: "pre-wrap" });

function UserCard({ user, choose }: { user: AdminUser; choose: () => void }) {
  const [copyError, setCopyError] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(user.userId);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  };
  return (
    <Card aria-label={user.nickname || user.email || user.userId}>
      <Typography variant="h3" component="h2">{user.nickname || "ニックネーム未設定"}</Typography>
      <LongText variant="body2">{user.email || "メールアドレス未取得"}</LongText>
      <Typography variant="caption" color="text.secondary">
        アカウント：{user.enabled ? "有効" : "無効"}
      </Typography>
      <LongText variant="caption" color="text.secondary">ユーザーID：{user.userId}</LongText>
      {copyError && <Alert severity="error">コピーできませんでした。</Alert>}
      <Controls>
        <Button variant="contained" onClick={choose}>履歴・詳細を見る</Button>
        <Button variant="outlined" onClick={() => { void copy(); }}>IDをコピー</Button>
      </Controls>
    </Card>
  );
}

function UserDetails({ adminSub, user, onBack }: {
  adminSub: string; user: AdminUser; onBack: () => void;
}) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<HistoryMode>("all");
  const [period, setPeriod] = useState<HistoryPeriod>("all");
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const { records, usage } = useAdminUserHistory(adminSub, user.userId, mode, period);
  const detail = useQuery({
    queryKey: [
      adminSub, "admin-user-feedback", user.userId,
      selected?.attemptId, selected?.evaluationId, "includeFollowUpReviews=1",
    ],
    queryFn: ({ signal }) =>
      getAdminUserFeedback(user.userId, selected!.attemptId!, selected!.evaluationId, signal),
    enabled: Boolean(selected?.attemptId && selected.status === "completed"),
  });
  useEffect(() => {
    setSelected(null);
    setMode("all");
    setPeriod("all");
  }, [user.userId]);
  const history = records.data?.pages.flatMap((page) => page.items) ?? [];
  const totals = usage.data?.usage;

  return (
    <Layout>
      <Controls><Button variant="outlined" onClick={onBack}>ユーザー一覧に戻る</Button></Controls>
      <Card>
        <Typography variant="h2" component="h1">{user.nickname || "ニックネーム未設定"}</Typography>
        <LongText>{user.email || "メールアドレス未取得"}</LongText>
        <Typography variant="body2">アカウント：{user.enabled ? "有効" : "無効"}</Typography>
        <LongText variant="caption">ユーザーID：{user.userId}</LongText>
        <NicknameEditor key={user.userId} resetKey={user.userId} nickname={user.nickname}
          onSave={async (nickname) => {
            await putAdminNickname(user.userId, nickname);
            await queryClient.invalidateQueries({ queryKey: [adminSub, "admin-users"] });
            if (adminSub === user.userId)
              await queryClient.invalidateQueries({ queryKey: [adminSub, "cognito-profile"] });
          }}
        />
      </Card>
      <Card>
        <Typography variant="h3" component="h2">利用状況（全期間）</Typography>
        {usage.isPending && <Typography role="status">利用状況を読み込み中…</Typography>}
        {usage.error && <Alert severity="error">利用状況を取得できませんでした。
          <Button onClick={() => { void usage.refetch(); }}>再試行</Button></Alert>}
        {totals && <Stats>
          {([
            ["回答した回数", totals.practiceAttempts + "件"],
            ["評価完了数", totals.evaluatedAttempts + "件"],
            ["AIで回答を作成した回数", totals.assistGenerations + "件"],
            ["AI回答チェック平均（100点満点）", totals.normalAverage ?? "―"],
            ["AI面接コーチ平均（30点満点）", totals.coachingAverage ?? "―"],
          ] as const).map(([label, value]) =>
            <Stat key={label}>
              <Typography variant="caption">{label}</Typography>
              <Typography variant="h3">{value}</Typography>
            </Stat>
          )}
        </Stats>}
      </Card>
      <Card>
        <Typography variant="h3" component="h2">練習履歴</Typography>
        <Filters>
          <FormControl size="small" fullWidth>
            <InputLabel id="admin-history-mode">モード</InputLabel>
            <Select labelId="admin-history-mode" label="モード" value={mode}
              onChange={(event) => { setMode(event.target.value as HistoryMode); setSelected(null); }}>
              <MenuItem value="all">すべて</MenuItem>
              <MenuItem value="normal">AI回答チェック</MenuItem>
              <MenuItem value="coaching">AI面接コーチ</MenuItem>
              <MenuItem value="assist">回答アシスト</MenuItem>
              {Object.entries(assistLabels).map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" fullWidth>
            <InputLabel id="admin-history-period">期間</InputLabel>
            <Select labelId="admin-history-period" label="期間" value={period}
              onChange={(event) => { setPeriod(event.target.value as HistoryPeriod); setSelected(null); }}>
              <MenuItem value="all">全期間</MenuItem>
              <MenuItem value="today">今日</MenuItem>
              <MenuItem value="7d">過去7日</MenuItem>
              <MenuItem value="30d">過去30日</MenuItem>
            </Select>
          </FormControl>
        </Filters>
        <HistoryList
          items={history} loading={records.isPending} error={records.error}
          loadingMore={records.isFetchingNextPage} hasMore={Boolean(records.hasNextPage)}
          onLoadMore={() => { void records.fetchNextPage(); }}
          onRetry={() => { void records.refetch(); }}
          onSelect={setSelected}
        />
      </Card>
      <Dialog open={Boolean(selected)} onClose={() => setSelected(null)}
        title="回答・評価詳細" maxWidth="md" fullWidth scrollContent
        content={selected && <Layout>
          <Typography variant="h3">{selected.label}</Typography>
          <Typography variant="caption">{formatHistoryDate(selected.createdAt)} ・ {historyStatus(selected)}</Typography>
          {selected.kind === "assist" ?
            <Alert severity="info">回答アシストの生成履歴です。評価点や生成本文は表示されません。</Alert> :
            selected.status !== "completed" ?
              <Alert severity="info">この回答の評価はまだ完了していません。</Alert> :
              detail.isPending ? <CircularProgress aria-label="評価詳細を読み込み中" /> :
              detail.error ? <Alert severity="error">
                {("status" in detail.error && detail.error.status === 409)
                  ? "この回答の評価はまだ完了していません。"
                  : "評価詳細を取得できませんでした。"}
                <Button onClick={() => { void detail.refetch(); }}>再試行</Button>
              </Alert> :
              detail.data && <FeedbackCard feedback={detail.data.feedback}
                followUpReviews={detail.data.followUpReviews} />}
        </Layout>}
        actions={<Button onClick={() => setSelected(null)}>閉じる</Button>}
      />
    </Layout>
  );
}

export function AdminUserManagement() {
  const { sub } = useAuthSession();
  const adminSub = sub ?? "";
  const [search, setSearch] = useState("");
  const [targetSub, setTargetSub] = useState<string | null>(null);
  const pages = useInfiniteQuery({
    queryKey: [adminSub, "admin-users"],
    queryFn: ({ pageParam, signal }) => getAdminUsers(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(adminSub),
  });
  useEffect(() => {
    setTargetSub(null);
    setSearch("");
  }, [adminSub]);
  const allUsers = pages.data?.pages.flatMap((page) => page.users) ?? [];
  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return term ? allUsers.filter((user) =>
      user.nickname?.toLocaleLowerCase().includes(term) ||
      user.email?.toLocaleLowerCase().includes(term)
    ) : allUsers;
  }, [search, allUsers]);
  const target = allUsers.find((user) => user.userId === targetSub);
  if (target && adminSub) return <UserDetails key={target.userId} adminSub={adminSub} user={target}
    onBack={() => setTargetSub(null)} />;
  return (
    <Layout>
      <Typography variant="h1" component="h1">ユーザー管理</Typography>
      <Typography variant="body2" color="text.secondary">
        登録ユーザーの履歴と利用状況を閲覧できます。回答や評価の編集はできません。
      </Typography>
      <TextField label="ニックネーム・メールアドレスで検索" fullWidth
        value={search} onChange={(event) => setSearch(event.target.value)} />
      {pages.hasNextPage && <Alert severity="info">読み込み済みユーザーから検索しています。</Alert>}
      {pages.isPending && <Typography role="status">ユーザー一覧を読み込み中…</Typography>}
      {pages.error && <Alert severity="error">ユーザー一覧を取得できませんでした。
        <Button onClick={() => { void pages.refetch(); }}>再試行</Button></Alert>}
      {filtered.length > 0 && <UserGrid>
        {filtered.map((user) => <UserCard key={user.userId} user={user}
          choose={() => setTargetSub(user.userId)} />)}
      </UserGrid>}
      {!pages.isPending && !pages.error && !filtered.length &&
        <Typography>該当するユーザーはいません。</Typography>}
      {pages.hasNextPage && <Controls><Button variant="outlined" disabled={pages.isFetchingNextPage}
        onClick={() => { void pages.fetchNextPage(); }}>
        {pages.isFetchingNextPage ? "読み込み中…" : "さらに読み込む"}
      </Button></Controls>}
    </Layout>
  );
}
