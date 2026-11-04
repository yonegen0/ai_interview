/** @file steps.ts @description 回答アシスト5モード共通の4ステップ・入力例。 */
import type { AssistMode } from "@/lib/api/schemas/star";

export type AssistStep = {
  key: "S" | "T" | "A" | "R";
  label: string;
  english: string;
  description: string;
  placeholder: string;
  tips: readonly string[];
};
const placeholder = "実際の経験や考えを箇条書きで入力（1〜3項目が目安）";

export const starSteps = [
  {
    key: "S", label: "状況", english: "Situation",
    description: "取り組みの背景や当時の状況を入力してください。",
    placeholder, tips: ["配送業務を担当していた", "顧客への提案を始めたばかりだった"],
  },
  {
    key: "T", label: "課題", english: "Task",
    description: "当時の問題・目標・役割を入力してください。",
    placeholder, tips: ["新しい顧客を増やしたかった", "提案方法を改善する必要があった"],
  },
  {
    key: "A", label: "行動", english: "Action",
    description: "自分で実際に行ったこと・工夫したことを入力してください。",
    placeholder, tips: ["顧客の困りごとをヒアリングした", "提案方法を何度も見直した"],
  },
  {
    key: "R", label: "結果・学び", english: "Result",
    description: "実際の結果・成果・学びを入力してください。",
    placeholder, tips: ["新規顧客を3社獲得した", "ヒアリングの重要性を学んだ"],
  },
] as const satisfies readonly AssistStep[];

const prepSteps = [
  {
    key: "S", label: "結論", english: "Point",
    description: "質問への答えを最初に簡潔に書いてください。",
    placeholder, tips: ["私の強みは主体性", "私の弱みは慎重になりすぎること"],
  },
  {
    key: "T", label: "理由", english: "Reason",
    description: "その考えに至った理由を箇条書きで入力してください。",
    placeholder, tips: ["自分で課題を見つけることが多い", "ミスを防ぐため確認を重視する"],
  },
  {
    key: "A", label: "具体例・補足", english: "Example",
    description: "経験がない仮定質問では、判断理由や対応方針でも構いません。",
    placeholder, tips: ["業務改善案を自分から提案した", "確認に時間がかかることがあった"],
  },
  {
    key: "R", label: "仕事への活かし方", english: "Point",
    description: "今後の仕事でどう活かすか入力してください。",
    placeholder, tips: ["入社後も主体的に行動したい", "優先順位を決めて効率を改善したい"],
  },
] as const satisfies readonly AssistStep[];

const motivationSteps = [
  {
    key: "S", label: "志望理由", english: "Why",
    description: "業界・職種・会社を志望する理由を入力してください。",
    placeholder, tips: ["人のキャリアを支えたい", "顧客の課題解決に関わりたい"],
  },
  {
    key: "T", label: "企業・業界の魅力", english: "Appeal",
    description: "自分で確認した企業・業界の特徴だけを入力してください。",
    placeholder, tips: ["顧客に寄り添うサービス方針", "専門性の高いサービスを提供している"],
  },
  {
    key: "A", label: "自分との接点", english: "Fit",
    description: "志望先と自身の経験・強みがつながる点を入力してください。",
    placeholder, tips: ["顧客の悩みを聞いて提案した経験", "自分から行動して成果につなげた経験"],
  },
  {
    key: "R", label: "入社後の貢献", english: "Contribution",
    description: "入社後に取り組みたいことを入力してください。",
    placeholder, tips: ["顧客との信頼関係を築きたい", "課題に合った提案をしたい"],
  },
] as const satisfies readonly AssistStep[];

const careerChangeSteps = [
  {
    key: "S", label: "転職のきっかけ", english: "Motivation",
    description: "転職を考え始めた出来事や気持ちを入力してください。",
    placeholder, tips: ["顧客への提案にやりがいを感じた", "営業を主な仕事にしたくなった"],
  },
  {
    key: "T", label: "現状と課題", english: "Situation",
    description: "働き方や役割で実際に感じている課題を入力してください。",
    placeholder, tips: ["集配業務が中心になっている", "営業活動に使える時間が限られている"],
  },
  {
    key: "A", label: "取り組み・考えたこと", english: "Actions",
    description: "実際の行動や検討したことを記入してください。架空の努力は不要です。",
    placeholder, tips: ["限られた時間で自主的に提案した", "今後のキャリアについて考えた"],
  },
  {
    key: "R", label: "次の職場で実現したいこと", english: "Goal",
    description: "次に挑戦したい仕事・長期的に伸ばしたい力を入力してください。",
    placeholder, tips: ["営業活動に集中したい", "長期的に営業スキルを磨きたい"],
  },
] as const satisfies readonly AssistStep[];

const careerPlanSteps = [
  {
    key: "S", label: "目指す姿", english: "Goal",
    description: "3年後・5年後など指定された時期の目標を入力してください。",
    placeholder, tips: ["3年後に営業として安定した成果を出したい", "顧客から信頼される存在になりたい"],
  },
  {
    key: "T", label: "その理由", english: "Reason",
    description: "その将来像を目指す理由を入力してください。",
    placeholder, tips: ["顧客の役に立ちたい", "長期的に専門性を高めたい"],
  },
  {
    key: "A", label: "必要な経験・能力", english: "Skills",
    description: "目標に向けて必要な経験・知識・スキルを入力してください。",
    placeholder, tips: ["ヒアリング力", "提案力と業界知識"],
  },
  {
    key: "R", label: "今後の行動", english: "Action",
    description: "入社後から実践したい具体的な行動を入力してください。",
    placeholder, tips: ["先輩の仕事の進め方を学ぶ", "定期的に成果を振り返る"],
  },
] as const satisfies readonly AssistStep[];

export const assistModes = {
  star: {
    label: "STARアシスト", tag: "エピソードを整理",
    description: "経験を4つのステップで整理し、A/B/Cの3案を生成します。",
    steps: starSteps,
  },
  prep: {
    label: "PREPアシスト", tag: "考えを分かりやすく",
    description: "結論・理由・具体例・活かし方を整理し、1案を生成します。",
    steps: prepSteps,
  },
  motivation: {
    label: "志望動機アシスト", tag: "志望理由を整理",
    description: "志望理由と自身との接点を整理し、1案を生成します。",
    steps: motivationSteps,
  },
  career_change: {
    label: "転職理由アシスト", tag: "前向きに伝える",
    description: "事実を維持したまま転職理由を整理し、1案を生成します。",
    steps: careerChangeSteps,
  },
  career_plan: {
    label: "キャリアプランアシスト", tag: "将来像を整理",
    description: "目指す姿と必要な行動を整理し、1案を生成します。",
    steps: careerPlanSteps,
  },
} as const satisfies Record<AssistMode, {
  label: string;
  tag: string;
  description: string;
  steps: readonly AssistStep[];
}>;
