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
    placeholder, tips: [
      "申請内容を転記する業務で、確認漏れが起きていた",
      "受付で来客対応を担当し、混雑する時間帯があった",
      "複数部署の連携業務で、依頼内容に認識のずれがあった",
    ],
  },
  {
    key: "T", label: "課題", english: "Task",
    description: "当時の問題・目標・役割を入力してください。",
    placeholder, tips: [
      "確認漏れを減らし、作業の正確さを高める必要があった",
      "待ち時間への不安を減らし、案内の質を保つ必要があった",
      "手戻りを防ぎ、期限内に業務を終える必要があった",
    ],
  },
  {
    key: "A", label: "行動", english: "Action",
    description: "自分で実際に行ったこと・工夫したことを入力してください。",
    placeholder, tips: [
      "漏れやすい項目を洗い出し、確認表を作った",
      "待ち時間の目安を伝え、問い合わせに順番に対応した",
      "各担当者と優先順位を確認し、決定事項を共有した",
    ],
  },
  {
    key: "R", label: "結果・学び", english: "Result",
    description: "実際の結果・成果・学びを入力してください。",
    placeholder, tips: [
      "確認漏れが減り、決まった手順で見直す重要性を学んだ",
      "案内によって相手の不安が和らぎ、伝え方の工夫を学んだ",
      "手戻りを減らせたことから、事前の認識合わせの重要性を学んだ",
    ],
  },
] as const satisfies readonly AssistStep[];

const prepSteps = [
  {
    key: "S", label: "結論", english: "Point",
    description: "質問への答えを最初に簡潔に書いてください。",
    placeholder, tips: ["私の強みは、課題に気づいたら自分から行動できること","私の弱みは、慎重になりすぎて判断に時間がかかること","仕事では、相手との認識をそろえることを大切にしている"],
  },
  {
    key: "T", label: "理由", english: "Reason",
    description: "その考えに至った理由を箇条書きで入力してください。",
    placeholder, tips: ["目の前の課題をそのままにせず、改善したいから","ミスを防ごうとして、細かい点まで確認してしまうから","認識のずれがあると、手戻りやミスにつながるから"],
  },
  {
    key: "A", label: "具体例・補足", english: "Example",
    description: "経験がない仮定質問では、判断理由や対応方針でも構いません。",
    placeholder, tips: ["担当業務で気づいた問題に対し、改善方法を提案した","確認に時間をかけすぎて、作業が遅れたことがある","作業を始める前に、目的や担当範囲を確認した"],
  },
  {
    key: "R", label: "仕事への活かし方", english: "Point",
    description: "今後の仕事でどう活かすか入力してください。",
    placeholder, tips: ["入社後も課題を見つけ、自分から改善に取り組みたい","確認する内容に優先順位をつけ、正確さと速さを両立したい","周囲と認識を合わせ、手戻りの少ない仕事につなげたい"],
  },
] as const satisfies readonly AssistStep[];

const motivationSteps = [
  {
    key: "S", label: "志望理由", english: "Why",
    description: "業界・職種・会社を志望する理由を入力してください。",
    placeholder, tips: ["相手の困りごとを理解し、解決につなげる仕事がしたい","〇〇分野の知識を深め、専門性を活かして働きたい","業務の仕組みや手順を工夫し、仕事の質を高めたい"],
  },
  {
    key: "T", label: "企業・業界の魅力", english: "Appeal",
    description: "自分で確認した企業・業界の特徴だけを入力してください。",
    placeholder, tips: ["貴社の〇〇というサービスや方針に魅力を感じた","求人票に記載されている〇〇という仕事内容に魅力を感じた","公式サイトで紹介されている〇〇の取り組みに関心を持った"],
  },
  {
    key: "A", label: "自分との接点", english: "Fit",
    description: "志望先と自身の経験・強みがつながる点を入力してください。",
    placeholder, tips: ["相手の要望を聞き、必要な対応を考えた経験がある","これまで〇〇の業務を担当し、さらに知識を深めたいと感じた","これまでの業務で〇〇の手順を見直した経験がある"],
  },
  {
    key: "R", label: "入社後の貢献", english: "Contribution",
    description: "入社後に取り組みたいことを入力してください。",
    placeholder, tips: ["一人ひとりの状況に合った対応で貢献したい","専門知識を身につけ、担当業務の品質向上に貢献したい","業務を理解したうえで改善に取り組み、チームに貢献したい"],
  },
] as const satisfies readonly AssistStep[];

const careerChangeSteps = [
  {
    key: "S", label: "転職のきっかけ", english: "Motivation",
    description: "転職を考え始めた出来事や気持ちを入力してください。",
    placeholder, tips: ["現在の仕事で〇〇にやりがいを感じ、その仕事を中心に取り組みたいと思った","〇〇の業務を経験し、より専門的な仕事に挑戦したいと考えた","今後のキャリアを考え、長期的に力を発揮できる環境で働きたいと思った"],
  },
  {
    key: "T", label: "現状と課題", english: "Situation",
    description: "働き方や役割で実際に感じている課題を入力してください。",
    placeholder, tips: ["現在は別の業務が中心で、希望する仕事に携わる機会が限られている","現職では担当できる業務の範囲が限られ、さらに経験を広げることが難しい","現在の勤務条件や業務の進め方では、長期的に働くうえで課題を感じている"],
  },
  {
    key: "A", label: "取り組み・考えたこと", english: "Actions",
    description: "実際の行動や検討したことを記入してください。架空の努力は不要です。",
    placeholder, tips: ["現在の担当業務の中で、希望する仕事に関連する業務にも取り組んだ","これまでの経験を振り返り、今後身につけたいスキルを整理した","今後の働き方や希望する仕事内容について考え、優先したい条件を整理した"],
  },
  {
    key: "R", label: "次の職場で実現したいこと", english: "Goal",
    description: "次に挑戦したい仕事・長期的に伸ばしたい力を入力してください。",
    placeholder, tips: ["希望する仕事を中心に経験を積み、自分の強みを伸ばしたい","新しい分野の知識やスキルを身につけ、専門性を高めたい","腰を据えて働きながら、継続的に成長し成果を出したい"],
  },
] as const satisfies readonly AssistStep[];

const careerPlanSteps = [
  {
    key: "S", label: "目指す姿", english: "Goal",
    description: "3年後・5年後など指定された時期の目標を入力してください。",
    placeholder, tips: ["3年後には、担当業務を一人で進められるようになりたい","5年後には専門知識を身につけ、難しい課題にも対応できるようになりたい","3年後には周囲と協力し、業務改善を提案できるようになりたい"],
  },
  {
    key: "T", label: "その理由", english: "Reason",
    description: "その将来像を目指す理由を入力してください。",
    placeholder, tips: ["任せてもらえる仕事の幅を広げ、安定して成果を出したいから","自分の専門性を高め、より難しい仕事にも挑戦したいから","自分だけでなく、チーム全体の仕事の質を高めたいから"],
  },
  {
    key: "A", label: "必要な経験・能力", english: "Skills",
    description: "目標に向けて必要な経験・知識・スキルを入力してください。",
    placeholder, tips: ["業務全体の流れを理解する力と、優先順位を判断する力","担当分野の専門知識と、問題の原因を分析する力","周囲の意見を聞く力と、業務の課題を整理する力"],
  },
  {
    key: "R", label: "今後の行動", english: "Action",
    description: "入社後から実践したい具体的な行動を入力してください。",
    placeholder, tips: ["入社後は基本業務を確実に覚え、定期的に改善点を振り返る","日々の業務で疑問点を調べ、必要な知識を継続的に学ぶ","まず担当業務を理解し、気づいた課題を周囲に相談して改善に取り組む"],
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
  follow_up: {
    label: "深掘り回答アシスト", tag: "深掘り質問に答える",
    description: "思いついたことを箇条書きで入力してください",
    steps: [] as readonly AssistStep[],
  },
} as const satisfies Record<AssistMode, {
  label: string;
  tag: string;
  description: string;
  steps: readonly AssistStep[];
}>;
