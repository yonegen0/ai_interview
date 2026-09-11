/** @file InterviewPractice.tsx @description 質問・回答・評価の画面統合 */
"use client";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { idSchema } from "@/lib/api/schemas";
import { getQuestion } from "@/lib/api/interview";
import { getFeedback } from "@/lib/api/feedback";
import { ErrorView } from "@/components/organisms/ErrorView";
import { Link } from "@/components/atoms/Link";
import { PracticeForm } from "@/features/interview/components/templates/PracticeForm";
export const InterviewPractice = () => {
  const params = useSearchParams();
  const id = params.get("sessionId") ?? "";
  const valid = idSchema.safeParse(id).success;
  const retryFrom =
    params.get("mode") === "retry" ? params.get("fromAttemptId") : null;
  const origin = useQuery({
    queryKey: ["feedback", retryFrom],
    queryFn: ({ signal }) => getFeedback(retryFrom!, signal),
    enabled: !!retryFrom && idSchema.safeParse(retryFrom).success,
  });
  const query = useQuery({
    queryKey: ["session", id],
    queryFn: ({ signal }) => getQuestion(id, signal),
    enabled: valid,
  });
  if (!valid)
    return <ErrorView error={new Error("練習IDを確認してください。")} />;
  if (query.isPending) return <p role="status">質問を読み込んでいます…</p>;
  if (query.error)
    return <ErrorView error={query.error} retry={() => void query.refetch()} />;
  if (params.get("mode") === "retry") {
    if (!retryFrom || !idSchema.safeParse(retryFrom).success)
      return (
        <ErrorView error={new Error("再挑戦する回答IDを確認してください。")} />
      );
    if (origin.isPending) return <p role="status">元の質問を確認しています…</p>;
    if (origin.error)
      return (
        <ErrorView error={origin.error} retry={() => void origin.refetch()} />
      );
    if (
      origin.data.sessionId !== id ||
      origin.data.questionNumber !== query.data.questionNumber
    )
      return (
        <>
          <ErrorView
            error={
              new Error("練習が更新されています。現在の練習へ戻ってください。")
            }
          />
          <Link href={`/practice/session/?sessionId=${id}`}>
            現在の練習へ戻る
          </Link>
        </>
      );
  }
  return (
    <PracticeForm
      key={`${id}:${query.data.questionNumber}:${retryFrom}`}
      session={query.data}
      retryFrom={retryFrom}
    />
  );
};
