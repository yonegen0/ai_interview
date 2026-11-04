/** @file steps.ts @description STAR入力の4段階に共通する表示文言と入力ガイド。 */
export const starSteps = [
  {
    key: "S",
    label: "状況",
    english: "Situation",
    description: "取り組みの背景や、当時の状況を具体的に入力してください。",
    placeholder: "例：営業担当として、既存顧客への訪問と提案を担当していました。",
    tips: ["いつ・どこでの経験か", "どのような役割・担当だったか", "当時の状況や背景"],
  },
  {
    key: "T",
    label: "課題",
    english: "Task",
    description: "当時、どのような問題や目標があったのか入力してください。",
    placeholder: "例：新規利用が伸び悩み、お客様の課題を把握する必要がありました。",
    tips: ["解決すべき問題", "達成したかった目標", "自分に求められていた役割"],
  },
  {
    key: "A",
    label: "行動",
    english: "Action",
    description: "課題を解決するために、自分で考えて実行したことを入力してください。",
    placeholder: "例：利用状況をヒアリングし、提案内容を何度も見直しました。",
    tips: ["自分で考えたこと", "実際に取った行動", "工夫・改善したこと", "周囲との連携"],
  },
  {
    key: "R",
    label: "結果",
    english: "Result",
    description: "取り組みの結果と、そこから得られた学びを入力してください。",
    placeholder: "例：新たに3社の利用につながり、ヒアリングの重要性を学びました。",
    tips: ["実際の成果", "数字で示せる変化", "周囲からの評価", "経験から得た学び"],
  },
] as const;
