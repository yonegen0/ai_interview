/** @file HistoryDialog.tsx @description 利用履歴・利用状況と過去の評価結果を閲覧専用で表示する。 */
"use client";
import { useEffect, useState } from "react";
import {
  Alert, CircularProgress, FormControl, InputLabel, MenuItem,
  Select, Tab, Tabs, Typography,
} from "@mui/material";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { alpha, styled } from "@mui/material/styles";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/atoms/Button";
import { Dialog } from "@/components/organisms/Dialog";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
import { getFeedbackWithReviews } from "@/lib/api/feedback";
import { useHistory } from "../hooks/useHistory";
import { HistoryList, historyStatus, formatHistoryDate, assistLabels } from "./HistoryList";
import {
  type HistoryItem, type HistoryMode, type HistoryPeriod,
} from "@/lib/api/schemas/history";

const Container = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2.5),
  padding: theme.spacing(0.5, 0, 2),
}));
const Filters = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.spacing(1.5),
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
const Heading = styled("span")(({ theme }) => ({
  display: "inline-flex", alignItems: "center", gap: theme.spacing(1),
  color: theme.palette.primary.dark, fontWeight: 700,
}));
const Summary = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.spacing(1.5),
}));
const Stat = styled("div")(({ theme }) => ({
  border: "1px solid " + alpha(theme.palette.primary.main, 0.12),
  background: alpha(theme.palette.primary.light, 0.075),
  borderRadius: theme.shape.borderRadius,
  display: "grid", gap: theme.spacing(0.25), minWidth: 0,
  overflowWrap: "anywhere", padding: theme.spacing(2),
}));
const Details = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2),
  minWidth: 0, marginBottom: theme.spacing(2),
}));
export type HistoryTab = 0 | 1;

function UsagePanel({ owner, open, data, loading, error, quota, quotaLoading, quotaError, retry, retryQuota }: {
  owner: string; open: boolean;
  data: ReturnType<typeof useHistory>["usage"]["data"];
  loading: boolean; error: Error | null;
  quota: ReturnType<typeof useHistory>["quota"]["data"];
  quotaLoading: boolean; quotaError: Error | null;
  retry: () => void; retryQuota: () => void;
}) {
  if (!open || !owner) return null;
  const usage = data?.usage;
  return (
    <Container>
      <Typography variant="caption" color="text.secondary">
        正確に取得できる保存済みレコードのみ集計。回答アシストは履歴として確認可能な生成件数です。
      </Typography>
      {loading ? <Typography role="status">利用状況を読み込み中…</Typography> :
        error ? <Alert severity="error">利用状況を取得できませんでした。
          <Button onClick={retry}>再試行</Button>
        </Alert> :
        usage ? <Summary>
          <Stat><Typography variant="caption">回答した回数</Typography><Typography variant="h3">{usage.practiceAttempts}件</Typography></Stat>
          <Stat><Typography variant="caption">評価完了数</Typography><Typography variant="h3">{usage.evaluatedAttempts}件</Typography></Stat>
          <Stat><Typography variant="caption">AIで回答を作成した回数</Typography><Typography variant="h3">{usage.assistGenerations}件</Typography><Typography variant="caption" color="text.secondary">AI回答アシストの生成履歴を集計しています。生成途中や失敗した履歴を含む場合があります。</Typography></Stat>
          <Stat><Typography variant="caption">AI回答チェック平均（100点満点）</Typography><Typography variant="h3">{usage.normalAverage ?? "―"}</Typography></Stat>
          <Stat><Typography variant="caption">AI面接コーチ平均（30点満点）</Typography><Typography variant="h3">{usage.coachingAverage ?? "―"}</Typography></Stat>
        </Summary> :
        <Typography>正確な集計値を表示できません。</Typography>}
      <Typography variant="h3" component="h3">今月の回答アシスト利用枠</Typography>
      {quotaLoading ? <Typography role="status">利用枠を確認中…</Typography> :
        quotaError ? <Alert severity="error">利用枠を取得できませんでした。<Button onClick={retryQuota}>再試行</Button></Alert> :
        quota && <Summary>
          <Stat><Typography variant="caption">消費済み</Typography><Typography variant="h3">{quota.user.consumed}回</Typography></Stat>
          <Stat><Typography variant="caption">残りの利用枠</Typography><Typography variant="h3">{quota.user.remaining}回</Typography></Stat>
          <Stat><Typography variant="caption">処理待ちの回数</Typography><Typography variant="h3">{quota.user.reserved}回</Typography><Typography variant="caption" color="text.secondary">処理待ち・処理中のため、利用枠として確保されている回数です。</Typography></Stat>
        </Summary>}
    </Container>
  );
}

export function HistoryDialog({ open, onClose, owner, initialTab = 0 }: {
  open: boolean; onClose: () => void; owner: string; initialTab?: HistoryTab;
}) {
  const [tab, setTab] = useState<HistoryTab>(initialTab);
  const [mode, setMode] = useState<HistoryMode>("all");
  const [period, setPeriod] = useState<HistoryPeriod>("all");
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  useEffect(() => { if (!open) setSelected(null); }, [open, owner]);
  const { records, usage, quota } = useHistory(owner, open, mode, period, tab);
  const reuseRecords = mode === "all" && period === "all";
  const items = records.data?.pages.flatMap((page) => page.items) ?? [];
  const detail = useQuery({
    queryKey: [owner, "history-feedback", selected?.attemptId, selected?.evaluationId],
    queryFn: ({ signal }) => getFeedbackWithReviews(selected!.attemptId!, signal, selected!.evaluationId!),
    enabled: open && Boolean(owner && selected?.attemptId && selected.status === "completed"),
  });
  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        maxWidth="sm"
        fullWidth
        scrollContent
        title={<Heading><HistoryRoundedIcon aria-hidden="true" />利用履歴</Heading>}
        content={<Container>
          <Tabs value={tab} onChange={(_, value: HistoryTab) => setTab(value)} variant="fullWidth"
            aria-label="利用履歴の表示内容">
            <Tab label="練習履歴" />
            <Tab label="利用状況" />
          </Tabs>
          {tab === 0 ? (
            <>
              <Filters>
                <FormControl size="small" fullWidth>
                  <InputLabel id="history-mode-label">モード</InputLabel>
                  <Select labelId="history-mode-label" value={mode} label="モード"
                    onChange={(e) => setMode(e.target.value as HistoryMode)}>
                    <MenuItem value="all">すべてのモード</MenuItem>
                    <MenuItem value="normal">AI回答チェック</MenuItem>
                    <MenuItem value="coaching">AI面接コーチ</MenuItem>
                    <MenuItem value="assist">回答アシスト</MenuItem>
                    {Object.entries(assistLabels).map(([value, label]) =>
                      <MenuItem value={value} key={value}>{label}</MenuItem>)}
                  </Select>
                </FormControl>
                <FormControl size="small" fullWidth>
                  <InputLabel id="history-period-label">期間</InputLabel>
                  <Select labelId="history-period-label" value={period} label="期間"
                    onChange={(e) => setPeriod(e.target.value as HistoryPeriod)}>
                    <MenuItem value="all">すべての期間</MenuItem>
                    <MenuItem value="today">今日</MenuItem>
                    <MenuItem value="7d">過去7日</MenuItem>
                    <MenuItem value="30d">過去30日</MenuItem>
                  </Select>
                </FormControl>
              </Filters>
              <Typography variant="body1"><strong>最近の練習</strong></Typography>
              <HistoryList
                items={items}
                loading={records.isPending}
                error={records.error}
                loadingMore={records.isFetchingNextPage}
                hasMore={Boolean(records.hasNextPage)}
                onLoadMore={() => { void records.fetchNextPage(); }}
                onRetry={() => { void records.refetch(); }}
                onSelect={setSelected}
              />
            </>
          ) : (
            <UsagePanel owner={owner} open={open}
              data={reuseRecords ? records.data?.pages[0] : usage.data}
              loading={reuseRecords ? records.isPending : usage.isPending}
              error={reuseRecords ? records.error : usage.error}
              quota={quota.data} quotaLoading={quota.isPending} quotaError={quota.error}
              retry={() => { void (reuseRecords ? records.refetch() : usage.refetch()); }}
              retryQuota={() => { void quota.refetch(); }} />
          )}
        </Container>}
        actions={<Button onClick={onClose} startIcon={<CloseRoundedIcon />}>閉じる</Button>}
      />
      <Dialog
        open={Boolean(selected) && open}
        onClose={() => setSelected(null)}
        maxWidth="md"
        scrollContent
        title="履歴の詳細"
        content={selected ? <Details>
          <Typography variant="body1"><strong>{selected.label}</strong></Typography>
          <Typography variant="caption" color="text.secondary">
            {formatHistoryDate(selected.createdAt)} ・ {historyStatus(selected)}
          </Typography>
          {selected.kind === "assist" ?
            <Alert severity="info">
              利用したモード：{assistLabels[selected.assistType!]}。
              この画面では、回答アシストの利用履歴と生成状態を確認できます。生成した回答候補の本文は表示されません。
              この生成に評価点は付きません。
            </Alert> :
            selected.status !== "completed" ?
              <Alert severity="info">評価の状態：{historyStatus(selected)}。結果の全文を表示できません。</Alert> :
              detail.isPending ? <CircularProgress aria-label="評価結果を取得中" /> :
              detail.error ? <Alert severity="error">評価結果を取得できませんでした。
                <Button onClick={() => { void detail.refetch(); }}>再試行</Button>
              </Alert> :
              detail.data ? <FeedbackCard feedback={detail.data.feedback} followUpReviews={detail.data.followUpReviews} /> : null}
        </Details> : <></>}
        actions={<Button onClick={() => setSelected(null)}>閉じる</Button>}
      />
    </>
  );
}
