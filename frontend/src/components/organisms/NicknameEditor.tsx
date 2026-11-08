/** @file NicknameEditor.tsx @description Save and clear a display-only Cognito nickname. */
"use client";
import { useEffect, useState } from "react";
import { Alert, Button, CircularProgress, TextField, Typography } from "@mui/material";
import { styled } from "@mui/material/styles";
import { normalizeNickname } from "@/lib/auth/nickname";

const Panel = styled("section")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1.5), minWidth: 0,
  padding: theme.spacing(2), border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius, overflowWrap: "anywhere",
}));
const Controls = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", gap: theme.spacing(1),
  "& button": { minHeight: 44 },
}));

export function NicknameEditor({ nickname, onSave, resetKey }: {
  nickname: string | null;
  resetKey: string;
  onSave: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState(nickname ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  useEffect(() => {
    setValue(nickname ?? "");
    setError(null);
    setSuccess(false);
  }, [nickname, resetKey]);
  const persist = async (next: string) => {
    if (saving) return;
    let normalized: string;
    try {
      normalized = normalizeNickname(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "入力内容を確認してください。");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await onSave(normalized);
      setValue(normalized);
      setSuccess(true);
    } catch {
      setError("保存できませんでした。入力内容を残しています。もう一度お試しください。");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Panel aria-label="ニックネーム設定">
      <Typography variant="h3" component="h3">ニックネーム</Typography>
      <Typography variant="body2">現在：{nickname || "ニックネーム未設定"}</Typography>
      <TextField label="ニックネーム（24文字以内）" value={value} fullWidth
        disabled={saving} onChange={(e) => { setValue(e.target.value); setError(null); setSuccess(false); }}
        helperText="日本語・英数字・絵文字が使えます。同じ名前を複数人で使用できます。"
      />
      {error && <Alert severity="error">{error}</Alert>}
      {success && <Alert severity="success">ニックネームを保存しました。</Alert>}
      <Controls>
        <Button variant="contained" disabled={saving} onClick={() => { void persist(value); }}>
          {saving ? <><CircularProgress size={16} />保存中…</> : "保存する"}
        </Button>
        <Button variant="outlined" disabled={saving || !nickname}
          onClick={() => { void persist(""); }}>削除する</Button>
      </Controls>
    </Panel>
  );
}
