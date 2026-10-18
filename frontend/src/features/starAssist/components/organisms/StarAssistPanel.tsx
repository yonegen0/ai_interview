/** @file StarAssistPanel.tsx @description 保存状態とSTAR入力・生成・明示反映。 */
"use client";
import { useState } from "react";
import { styled } from "@mui/material/styles";
import { Radio, RadioGroup, FormControlLabel } from "@mui/material";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Select } from "@/components/atoms/Select";
import { Text } from "@/components/atoms/Text";
import { Actions } from "@/components/atoms/Actions";
import { Dialog } from "@/components/organisms/Dialog";
import { targetCategories, type StarInput } from "@/lib/api/schemas/star";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";
import { StarNotesFields, StarCandidateFields } from "../molecules/StarFields";
const Area = styled("section")(({ theme }) => ({
  marginBlock: theme.spacing(2),
  padding: theme.spacing(2),
  border: `1px solid ${theme.palette.divider}`,
  borderRadius: theme.shape.borderRadius,
}));
const Settings = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  marginBlock: theme.spacing(2),
}));
export function StarAssistPanel({
  workspace,
  hasAnswer,
}: {
  workspace: StarWorkspace;
  hasAnswer: boolean;
}) {
  const [open, setOpen] = useState(false),
    [confirm, setConfirm] = useState<
      "apply" | "load" | "mine" | "discardStar" | null
    >(null);
  const w = workspace;
  const apply = () => {
    if (hasAnswer) setConfirm("apply");
    else void w.apply();
  };
  return (
    <Area aria-label="回答の保存とSTARアシスト">
      <Text role="status" aria-live="polite">
        下書き：{w.status}
        {w.loading ? "（保存版を確認中）" : ""}
      </Text>
      {w.error && <Text role="alert">{w.error}</Text>}
      {w.migrationWarning && <Text role="alert">{w.migrationWarning}</Text>}
      <Actions>
        {w.pending && (
          <Button
            type="button"
            onClick={() => void w.recover()}
            disabled={w.busy}
          >
            保存結果を再確認
          </Button>
        )}
        {w.status === "競合" && (
          <>
            <Button type="button" onClick={() => void w.inspectSaved()}>
              保存版を確認
            </Button>
            <Button type="button" onClick={() => setConfirm("load")}>
              保存版を読み込む
            </Button>
            <Button
              type="button"
              onClick={() => setConfirm("mine")}
              disabled={w.pending || w.busy}
            >
              自分の内容を保存
            </Button>
          </>
        )}
        {w.savedPreview !== null && <Text>現在の保存版：{w.savedPreview}</Text>}
        {w.error && !w.pending && (
          <Button type="button" onClick={w.refresh}>
            補助保存を再読込み
          </Button>
        )}
        <Button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          STARアシスト{open ? "を閉じる" : "を開く"}
        </Button>
      </Actions>
      {open && (
        <>
          <Text variant="h2" component="h2">
            応募先向けのSTARアシスト
          </Text>
          <Text>
            正式送信するまで採点されません。生成した回答は、ご自身の事実に合うよう確認・編集してください。
          </Text>
          <Settings>
            <Select
              label="応募先カテゴリ"
              value={w.input.targetCategory ?? ""}
              disabled={w.busy}
              options={[
                { value: "", label: "選択してください" },
                ...Object.entries(targetCategories).map(([value, label]) => ({
                  value,
                  label,
                })),
              ]}
              onChange={(value) =>
                w.selectCategory((value || null) as StarInput["targetCategory"])
              }
            />
            <Button
              type="button"
              onClick={() => void w.savePreferences(true)}
              disabled={w.busy || w.pending || !w.input.targetCategory}
            >
              このカテゴリを14日保存
            </Button>
            <Input
              {...w.form.register("industry")}
              label="志望業界（任意）"
              disabled={w.busy}
            />
            <Input
              {...w.form.register("company")}
              label="応募先企業名（任意）"
              disabled={w.busy}
            />
            <Button
              type="button"
              onClick={() => void w.savePreferences()}
              disabled={w.busy || w.pending}
            >
              業界・企業名を14日保存
            </Button>
          </Settings>
          <StarNotesFields form={w.form} disabled={false} />
          <Button
            type="button"
            onClick={() => setConfirm("discardStar")}
            disabled={w.busy || w.pending || w.loading}
          >
            STAR下書きを破棄
          </Button>
          {w.quota && (
            <Text>
              今月の生成残り：あなた {w.quota.user.remaining} / 全体{" "}
              {w.quota.global.remaining}（JST {w.quota.month}）
            </Text>
          )}
          <Button
            type="button"
            onClick={() => void w.generate()}
            disabled={
              w.loading ||
              w.busy ||
              w.pending ||
              w.generating ||
              !w.input.targetCategory ||
              !Object.values(w.input.notes).some((v) => v.trim()) ||
              !w.form.formState.isValid ||
              w.quota?.user.remaining === 0 ||
              w.quota?.global.remaining === 0
            }
          >
            {w.generating
              ? "3案を生成しています…"
              : w.input.candidates.length
                ? "新カテゴリ・メモで再生成（1回）"
                : "3案を生成（1回）"}
          </Button>
          {w.resultWaiting && (
            <>
              <Text>
                生成中に編集が進みました。結果で入力を上書きしていません。
              </Text>
              <Button type="button" onClick={w.adopt}>
                生成結果を採用する
              </Button>
            </>
          )}
          {w.generationCategory && (
            <Text>
              現在の3案の生成時カテゴリ：
              {targetCategories[w.generationCategory]}
            </Text>
          )}
          <StarCandidateFields form={w.form} input={w.input} disabled={false} />
          {w.input.candidates.length > 0 && (
            <>
              <RadioGroup
                aria-label="反映する回答案"
                value={w.input.selectedCandidateId ?? ""}
                onChange={(_, value) =>
                  w.form.setValue(
                    "selectedCandidateId",
                    value as "A" | "B" | "C",
                    { shouldDirty: true, shouldValidate: true },
                  )
                }
              >
                {w.input.candidates.map((c) => (
                  <FormControlLabel
                    key={c.id}
                    value={c.id}
                    control={<Radio />}
                    label={`案${c.id}を選択`}
                  />
                ))}
              </RadioGroup>
              <Button
                type="button"
                onClick={apply}
                disabled={
                  !w.input.selectedCandidateId ||
                  w.busy ||
                  w.pending ||
                  !w.form.formState.isValid
                }
              >
                この回答を反映
              </Button>
            </>
          )}
        </>
      )}
      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title={
          confirm === "apply"
            ? "入力中の回答を置き換えますか？"
            : confirm === "discardStar"
              ? "STAR下書きを破棄しますか？"
              : confirm === "mine"
                ? "自分の内容で保存版を更新しますか？"
                : "保存版を読み込みますか？"
        }
        content={
          <Text>
            {confirm === "mine"
              ? "最新の保存版を確認して、自分の内容を新しい要求で保存します。"
              : confirm === "discardStar"
                ? "STARメモと3案を破棄します。通常回答の入力は保持します。"
                : "入力中の内容を置き換えます。"}
            正式送信・評価は開始しません。
          </Text>
        }
        actions={
          <>
            <Button type="button" onClick={() => setConfirm(null)}>
              キャンセル
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (confirm === "apply") void w.apply();
                else if (confirm === "mine") void w.saveMine();
                else if (confirm === "discardStar") void w.discardStar();
                else void w.loadSaved();
                setConfirm(null);
              }}
            >
              {confirm === "mine"
                ? "確認して保存"
                : confirm === "discardStar"
                  ? "破棄する"
                  : "置き換える"}
            </Button>
          </>
        }
      />
    </Area>
  );
}
