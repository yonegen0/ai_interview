/** @file HistoryList.tsx @description 種別・評価状態を区別して本人履歴を表示する。 */
"use client";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import { Alert, CircularProgress, Typography } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import type { HistoryItem } from "@/lib/api/schemas/history";
import { ApiError } from "@/lib/api/client";

const List = styled("ul")(({ theme }) => ({
  listStyle: "none", margin: 0, padding: 0, display: "grid",
  borderRadius: theme.shape.borderRadius, overflow: "hidden",
  border: "1px solid " + theme.palette.divider,
}));
const Row = styled("li")(({ theme }) => ({
  borderBottom: "1px solid " + theme.palette.divider,
  "&:last-child": { borderBottom: 0 },
}));
const RowButton = styled("button")(({ theme }) => ({
  width: "100%", display: "flex", alignItems: "center",
  gap: theme.spacing(1.5), padding: theme.spacing(1.5),
  border: "none", backgroundColor: "transparent",
  color: theme.palette.text.primary, textAlign: "left", cursor: "pointer",
  "&:hover": { backgroundColor: alpha(theme.palette.primary.main, 0.055) },
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.main, outlineOffset: -3 },
}));
const Glyph = styled("span")(({ theme }) => ({
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  flexShrink: 0, width: 42, height: 42, borderRadius: 14,
  backgroundColor: alpha(theme.palette.primary.light, 0.16),
  color: theme.palette.primary.dark,
}));
const Details = styled("span")(({ theme }) => ({
  minWidth: 0, flex: 1, display: "grid", gap: theme.spacing(0.25),
  "& > strong": { overflowWrap: "anywhere" },
}));
const Score = styled("span")(({ theme }) => ({
  display: "inline-flex", flexShrink: 0, alignItems: "center",
  borderRadius: 50, padding: theme.spacing(0.5, 1),
  background: alpha(theme.palette.success.light, 0.18),
  color: theme.palette.primary.dark, fontWeight: 700,
  fontSize: theme.typography.caption.fontSize,
}));
const AssistNames = {
  star: "STAR", prep: "PREP", motivation: "志望動機",
  career_change: "転職理由", career_plan: "キャリアプラン",
};
export const formatHistoryDate = (ms: number) =>
  new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(ms));
export function historyStatus(item: HistoryItem) {
  const names: Record<string, string> = {
    processing: "評価中", completed: "評価完了", failed: "評価失敗",
    QUEUED: "生成待ち", PREPARED: "準備中", STARTED: "生成中",
    SUCCEEDED: "生成完了", NEEDS_INFORMATION: "追加情報が必要",
    CANCELLED: "キャンセル", FAILED_BEFORE_START: "生成失敗",
    FAILED_AFTER_START: "生成失敗", OUTCOME_UNKNOWN: "結果未確定",
  };
  return names[item.status] ?? "状態不明";
}
export function HistoryList({
  items, loading, error, loadingMore, hasMore, onLoadMore, onRetry, onSelect,
}: {
  items: HistoryItem[];
  loading: boolean;
  error: Error | null;
  loadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onRetry: () => void;
  onSelect: (item: HistoryItem) => void;
}) {
  if (loading) return <Typography role="status">履歴を読み込んでいます…</Typography>;
  if (error && items.length === 0)
    return (
      <Alert severity="error" action={<Button onClick={onRetry}>再試行</Button>}>
        {error instanceof ApiError && error.code === "HISTORY_SEARCH_LIMIT"
          ? "検索範囲を超えたため、正確な履歴を表示できません。"
          : "履歴を取得できませんでした。"}
      </Alert>
    );
  if (!items.length) return <Typography>この条件に一致する履歴はありません。</Typography>;
  return (
    <>
      <List aria-label="練習履歴">
        {items.map((item) => (
          <Row key={item.id}>
            <RowButton type="button" onClick={() => onSelect(item)} aria-label={`${item.label}の詳細を見る`}>
              <Glyph aria-hidden="true">{item.kind === "assist"
                ? <AutoAwesomeOutlinedIcon /> : <HistoryRoundedIcon />}</Glyph>
              <Details>
                <strong>{item.label}</strong>
                <Typography variant="caption" color="text.secondary" component="span">
                  {formatHistoryDate(item.createdAt)} ・
                  {item.kind === "normal" ? "通常練習" :
                    item.kind === "coaching" ? "Coaching V2" : AssistNames[item.assistType!]}
                  {" ・ "}{historyStatus(item)}
                </Typography>
              </Details>
              {item.score !== null && <Score>{item.score}/{item.scoreMax}点</Score>}
              <ChevronRightRoundedIcon color="action" fontSize="small" />
            </RowButton>
          </Row>
        ))}
      </List>
      {error && <Alert severity="error">追加履歴を取得できませんでした。
        <Button onClick={onLoadMore}>再試行</Button>
      </Alert>}
      {hasMore && <Button onClick={onLoadMore} disabled={loadingMore}>
        {loadingMore ? <><CircularProgress size={16} /> 読み込み中…</> : "さらに5件表示"}
      </Button>}
      {!hasMore && <Typography variant="caption" color="text.secondary">表示可能な履歴は以上です。</Typography>}
    </>
  );
}
