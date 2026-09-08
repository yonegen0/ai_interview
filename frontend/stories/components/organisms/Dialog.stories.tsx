/**
 * @file Dialog.stories.tsx
 * @description 共通 Dialog の表示確認。Outlined Input のラベル見切れ・長コンテンツを検証する
 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import DialogContentText from "@mui/material/DialogContentText";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Typography from "@mui/material/Typography";
import { styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Dialog } from "@/components/organisms/Dialog";
import { withMobileDialogWidth } from "../../test-utils/withMobileDialogWidth";

const meta: Meta<typeof Dialog> = {
  title: "Components/Organisms/Dialog",
  component: Dialog,
  parameters: { layout: "fullscreen" },
  args: {
    open: true,
    onClose: () => {},
    title: "ダイアログ",
    content: null,
    actions: null,
  },
};

export default meta;
type Story = StoryObj<typeof Dialog>;

/** 警告文（DiagnoseNoteDialog 相当） */
const StyledWarning = styled(Typography)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  fontWeight: 600,
  color: theme.palette.text.primary,
}));

/** WithOutlinedInput: ラベル浮上時の見切れ確認 */
export const WithOutlinedInput: Story = {
  decorators: [withMobileDialogWidth],
  render: () => {
    const [note, setNote] = useState("");
    return (
      <Dialog
        open
        onClose={() => {}}
        title="入力テスト"
        content={
          <Input
            label="特記事項（任意）"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="入力してください"
          />
        }
        actions={
          <>
            <Button color="inherit">キャンセル</Button>
            <Button color="primary" variant="contained">
              確定
            </Button>
          </>
        }
      />
    );
  },
};

/** WithMultilineInput: DiagnoseNoteDialog 相当 */
export const WithMultilineInput: Story = {
  decorators: [withMobileDialogWidth],
  render: () => {
    const [note, setNote] = useState("");
    return (
      <Dialog
        open
        onClose={() => {}}
        title="診断を生成"
        content={
          <>
            <StyledWarning variant="body1">
              現在の診断結果は新しい内容で上書きされ、元には戻せません。
            </StyledWarning>
            <Input
              label="特記事項（任意）"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              multiline
              minRows={2}
              placeholder="例：今月から朝割を開始"
              helperText="数値に表れない補足を分析に反映します。"
            />
          </>
        }
        actions={
          <>
            <Button color="inherit">キャンセル</Button>
            <Button color="primary" variant="contained">
              生成する
            </Button>
          </>
        }
      />
    );
  },
};

/** WithLongContent: 縦長コンテンツ（スクロール退行の確認用） */
export const WithLongContent: Story = {
  render: () => (
    <Dialog
      open
      onClose={() => {}}
      title="集約"
      content={
        <>
          <FormControl fullWidth>
            <InputLabel id="dialog-story-period">集約対象の期間</InputLabel>
            <Select labelId="dialog-story-period" label="集約対象の期間" value="">
              <MenuItem value="">2026年5月</MenuItem>
            </Select>
          </FormControl>
          <ul>
            {Array.from({ length: 12 }, (_, i) => (
              <li key={i}>
                <Typography variant="body2">2026-W{String(i + 1).padStart(2, "0")}</Typography>
              </li>
            ))}
          </ul>
        </>
      }
      actions={
        <>
          <Button color="inherit">キャンセル</Button>
          <Button color="primary" variant="contained">
            集約を実行
          </Button>
        </>
      }
    />
  ),
};

/** ConfirmOnly: 最小構成 */
export const ConfirmOnly: Story = {
  args: {
    title: "確認",
    content: (
      <DialogContentText>この操作を実行します。よろしいですか？</DialogContentText>
    ),
    actions: (
      <>
        <Button color="inherit">キャンセル</Button>
        <Button color="primary" variant="contained">
          実行
        </Button>
      </>
    ),
  },
};
