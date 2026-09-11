/** @file PracticeStart.tsx @description カテゴリ選択と冪等なセッション作成 */
"use client";
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { styled } from "@mui/material/styles";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { Muted } from "@/components/atoms/Muted";
import { Panel } from "@/components/atoms/Panel";
import { MascotCharacter } from "@/components/atoms/MascotCharacter";
import { ErrorView } from "@/components/organisms/ErrorView";
import { categories, type Category } from "@/lib/api/schemas";
import { createSession } from "@/lib/api/interview";
import { uncertain } from "@/lib/api/client";
import {
  operationSchema,
  readSaved,
  save,
  removeSaved,
} from "@/lib/storage/recovery";
const Introduction = styled("div")({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  alignItems: "center",
  gap: 12,
  "@media (min-width: 768px)": { gap: 24 },
});
const IntroductionText = styled("div")({ minWidth: 0 });
const Grid = styled("div")({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
  gap: 12,
});
const Choice = styled("button")(({ theme }) => ({
  font: "inherit",
  padding: "22px 18px",
  minHeight: 70,
  textAlign: "left",
  border: "1px solid #b6c4ae",
  borderRadius: 16,
  background: "#fff",
  color: theme.palette.text.primary,
  cursor: "pointer",
  "&[aria-pressed=true]": {
    background: "#e4eddd",
    border: `2px solid ${theme.palette.primary.dark}`,
  },
  "&:disabled": { cursor: "wait" },
}));
export const PracticeStart = () => {
  const router = useRouter();
  const [category, setCategory] = useState<Category | null>(null);
  const pending = useRef<ReturnType<typeof operationSchema.parse> | null>(null);
  const [recovering, setRecovering] = useState(false);
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    const restored = readSaved("pocket:create", operationSchema);
    if (restored?.category) {
      pending.current = restored;
      setCategory(restored.category);
      setRecovering(true);
    }
    setRestoring(false);
  }, []);
  const locked = useRef(false);
  const mutation = useMutation({
    mutationFn: ({ category, key }: { category: Category; key: string }) =>
      createSession(category, key),
  });
  const start = async () => {
    if (locked.current || (!category && !pending.current?.category)) return;
    locked.current = true;
    const request = pending.current ?? {
      version: 1 as const,
      key: crypto.randomUUID(),
      category: category!,
    };
    pending.current = request;
    save("pocket:create", request);
    try {
      const value = await mutation.mutateAsync({
        category: request.category!,
        key: request.key,
      });
      removeSaved("pocket:create");
      router.push(`/practice/session/?sessionId=${value.sessionId}`);
    } catch (error) {
      if (uncertain(error)) setRecovering(true);
      else {
        pending.current = null;
        removeSaved("pocket:create");
        setRecovering(false);
      }
    } finally {
      locked.current = false;
    }
  };
  return (
    <>
      <Introduction>
        <IntroductionText>
          <Muted>QUICK PRACTICE · 約3分</Muted>
          <h1>今日は何を練習しますか？</h1>
          <Muted>カテゴリを選んで、一問だけ。難易度は標準です。</Muted>
        </IntroductionText>
        <MascotCharacter variant="welcome" size="lg" loading="eager" />
      </Introduction>
      <Panel>
        <Grid>
          {(Object.keys(categories) as Category[]).map((key) => (
            <Choice
              key={key}
              type="button"
              aria-pressed={category === key}
              disabled={restoring || mutation.isPending || recovering}
              onClick={() => setCategory(key)}
            >
              {categories[key]}
            </Choice>
          ))}
        </Grid>
        <Actions>
          <Button
            disabled={
              restoring || mutation.isPending || (!category && !recovering)
            }
            onClick={start}
          >
            {mutation.isPending
              ? "練習を準備しています…"
              : recovering
                ? "開始結果を再確認"
                : "練習を始める"}
          </Button>
        </Actions>
        {mutation.error && <ErrorView error={mutation.error} />}
      </Panel>
    </>
  );
};
