/** @file questions.ts @description 7カテゴリ各3問の固定質問 */
import { categories, type Category, type Question } from "@/lib/api/schemas";
const texts: Record<Category, string[]> = {
  job_change: [
    "転職を考えた理由を教えてください。",
    "次の職場で実現したいことは何ですか？",
    "現職では実現が難しいと感じたことを教えてください。",
  ],
  motivation: [
    "当社を志望した理由を教えてください。",
    "当社の事業のどこに魅力を感じますか？",
    "入社後、どのように貢献したいですか？",
  ],
  strengths: [
    "あなたの強みを具体例とともに教えてください。",
    "周囲からよく評価される点は何ですか？",
    "強みを仕事で活かした経験を教えてください。",
  ],
  experience: [
    "これまでの仕事で最も力を入れたことは何ですか？",
    "チームで成果を出した経験を教えてください。",
    "業務を改善した経験を教えてください。",
  ],
  difficulty: [
    "仕事で困難を乗り越えた経験を教えてください。",
    "失敗から学んだことは何ですか？",
    "意見が対立した際、どう対応しましたか？",
  ],
  career: [
    "3年後、どのような仕事をしていたいですか？",
    "今後身につけたい能力は何ですか？",
    "仕事で大切にしている価値観を教えてください。",
  ],
  questions: [
    "面接官に確認したいことは何ですか？",
    "入社後の期待を確認する質問を考えてください。",
    "チームの働き方について、どのように質問しますか？",
  ],
};
export const questions: Question[] = (
  Object.keys(categories) as Category[]
).flatMap((category, i) =>
  texts[category].map((question, j) => ({
    id: `00000000-0000-4000-8000-${String(i * 3 + j + 1).padStart(12, "0")}`,
    category,
    difficulty: "standard",
    question,
  })),
);
