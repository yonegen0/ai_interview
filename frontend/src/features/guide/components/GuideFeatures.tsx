/** @file GuideFeatures.tsx @description 七つの機能別ガイドと静的アシスト選択案内。 */
"use client";

import { useEffect, useState } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, FormControl,
  InputLabel, MenuItem, Select,
} from "@mui/material";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import {
  GuideBack, GuideEyebrow, GuideHeading, GuideLead, GuidePage, GuideSubheading,
  GuideSurface,
} from "./GuideUI";

type Entry = {
  title: string;
  when: string;
  does: string;
  steps: readonly string[];
  note?: string;
  href?: string;
  linkLabel?: string;
};
type Category = { id: string; title: string; introduction: string; entries: readonly Entry[] };
const categories: readonly Category[] = [
  {
    id: "practice", title: "練習の始め方", introduction: "目的に合う入口を選びましょう。",
    entries: [
      { title: "カテゴリから選ぶ", when: "練習したいテーマが決まっているとき。",
        does: "テーマ別に質問を選んで練習できます。",
        steps: ["ホームで「カテゴリから選ぶ」を押す", "テーマを選び「練習を始める」を押す"],
        href: "/practice/category/", linkLabel: "カテゴリを選ぶ" },
      { title: "3分から始める", when: "何を練習するか迷ったとき。",
        does: "未完了の質問を先頭から確認し、1問の練習を始めます。",
        steps: ["ホームで「3分から始める」を押す", "既存の練習・下書きがあれば確認・復元して進む"],
        note: "全問完了している場合は達成画面から復習へ進めます。必ず3分以内に終わるという意味ではありません。",
        href: "/practice/quick/", linkLabel: "3分から始める" },
      { title: "通し練習", when: "一通りの質問に順番に取り組みたいとき。",
        does: "用意された質問を順番に練習できます。",
        steps: ["練習開始画面で「全質問を順番に練習」を選ぶ", "「練習を始める」を押す"],
        href: "/practice/", linkLabel: "練習開始画面へ" },
      { title: "15問進捗", when: "残りの質問を確認したいとき。",
        does: "ホームの進捗カードで完了数・残り・進捗バーを確認できます。",
        steps: ["ホームの「面接練習の進捗」を確認する", "未完了の質問へ挑戦する"],
        note: "初回評価が正常に完了した質問IDで集計され、再挑戦や深掘りを重複加算しません。",
        href: "/", linkLabel: "ホームを見る" },
    ],
  },
  {
    id: "assist", title: "回答アシスト", introduction: "メモから回答を整えたいときに。",
    entries: [
      { title: "エピソード作成アシスト", when: "具体的な経験や自己PRを伝えたいとき。",
        does: "経験や行動、成果を整理して、面接で伝わる3つの回答案を作成します。",
        steps: ["回答作成画面でエピソード作成アシストを開く", "4項目のメモなどを入力して生成する", "3案を比較・必要なら編集して反映する"] },
      { title: "簡潔回答アシスト", when: "強み・弱み・考え方を結論から話したいとき。",
        does: "結論・理由・具体例を整理して、わかりやすく伝わる回答案を作成します。",
        steps: ["簡潔回答アシストを開く", "画面の項目に沿って入力・生成する", "内容を確認し回答欄へ反映する"] },
      { title: "志望動機アシスト", when: "応募先への志望理由を整理したいとき。",
        does: "会社を選ぶ理由や自分との接点を整理して1案作ります。",
        steps: ["志望動機アシストを開く", "応募先との接点などを入力する", "確認・編集して反映する"] },
      { title: "転職理由アシスト", when: "転職のきっかけを前向きに説明したいとき。",
        does: "経験や希望に一貫性のある回答を1案作ります。",
        steps: ["転職理由アシストを開く", "きっかけ・課題・次に実現したいことを入力する", "事実を確認して反映する"] },
      { title: "キャリアプランアシスト", when: "将来の目標を説明したいとき。",
        does: "目標・理由・必要な経験・行動を整理した回答を1案作ります。",
        steps: ["キャリアプランアシストを開く", "目指す姿などを入力する", "確認・編集して反映する"] },
      { title: "深掘り回答アシスト", when: "追加質問にどう答えるか迷ったとき。",
        does: "追加質問に対する箇条書きメモから回答例を1案作ります。",
        steps: ["AI面接コーチで追加質問が表示されたらアシストを開く", "思いついたことを箇条書きで入力して生成", "内容を確認して回答欄へ反映する"],
        note: "初回の質問に対する通常のアシストとは利用場面が異なります。" },
    ],
  },
  {
    id: "evaluation", title: "AI採点・評価", introduction: "得点だけでなく、改善のヒントを確認しましょう。",
    entries: [
      { title: "AI回答チェック", when: "一般的な面接回答を振り返りたいとき。",
        does: "100点満点の評価と、良かった点・改善ポイントを確認できます。",
        steps: ["通常練習で回答を送信する", "評価完了後に総合評価とアドバイスを確認する"] },
      { title: "AI面接コーチ", when: "より詳しいフィードバックや追加質問を受けたいとき。",
        does: "30点満点の総合評価を中心に振り返れます。",
        steps: ["AI面接コーチの対象となる回答を送信する", "総合評価と項目別の結果を確認する"],
        note: "表示内容は練習の種類や評価状態で異なります。" },
      { title: "評価結果の見方", when: "次に何を直すか考えたいとき。",
        does: "総合評価、良かった点、改善ポイント、提供される場合は回答例・改善回答を確認できます。",
        steps: ["まず良かった点で継続したいことを確認", "改善ポイントを1つ選び、再挑戦で意識する"],
        note: "回答例・改善回答は評価モードや結果によって表示されない場合があります。" },
    ],
  },
  {
    id: "followup", title: "深掘り質問", introduction: "面接官からの追加質問に答える練習です。",
    entries: [
      { title: "深掘り質問とは？", when: "最初の回答について、さらに詳しく説明するとき。",
        does: "AI面接コーチでは最大3回の追加質問に答えることがあります。",
        steps: ["初回の評価後、表示された追加質問を読む", "具体的な判断・行動・理由を自分の言葉で答える"],
        note: "追加質問の進み方は現在のセッション状態に従います。" },
      { title: "深掘り回答アシスト", when: "追加質問への回答がまとまらないとき。",
        does: "短いメモから回答例を生成できます。",
        steps: ["追加質問の回答画面で「深掘り回答アシスト」を開く", "箇条書きでメモを入力し、生成結果を確認する"],
        href: "/guide/features/#assist", linkLabel: "アシストの種類を見る" },
      { title: "深掘り回答の評価", when: "追加質問への答えを振り返りたいとき。",
        does: "利用環境で専用評価が有効な場合、回答へのアドバイスや30点満点の評価を確認できます。",
        steps: ["深掘り回答を送信する", "評価が提供されている場合は結果・改善点を確認する"],
        note: "専用採点は環境の機能設定によって異なります。すべての環境での表示は保証されません。" },
    ],
  },
  {
    id: "draft", title: "下書き・再挑戦", introduction: "途中の回答を見直し、繰り返し練習できます。",
    entries: [
      { title: "回答欄の下書き", when: "回答を途中まで書いているとき。",
        does: "この端末に下書きを保存し、条件が合えば復元できます。",
        steps: ["回答欄に入力し、保存状態を確認する", "同じ練習に戻ったとき、復元された内容を確認する"],
        note: "保存失敗・期限切れ・端末やセッションの違いなどで復元できない場合があります。" },
      { title: "回答アシストの作業内容", when: "アシストの入力メモや候補を見直したいとき。",
        does: "回答欄とは別に補助的な下書きが管理されます。",
        steps: ["該当するアシストを開く", "下書きの状態を確認し、必要なら保存版を確認する"],
        note: "端末側の回答下書き、サーバー側のアシスト下書き、送信済み・評価済み回答は別物です。" },
      { title: "同じ質問に再挑戦", when: "改善点を反映してやり直したいとき。",
        does: "同じ質問で改めて回答できます。",
        steps: ["評価後の画面で再挑戦を選ぶ", "表示される場合は「前回の回答をコピー」を使い、内容を修正して送信する"],
        note: "表示される操作は練習モードや状態によって異なります。" },
    ],
  },
  {
    id: "history", title: "進捗・履歴", introduction: "練習の積み重ねを確認しましょう。",
    entries: [
      { title: "15問進捗カード", when: "残りの質問が知りたいとき。",
        does: "ホーム画面に完了数と残りの質問数が表示されます。",
        steps: ["ホームの進捗カードを見る", "全問達成後はカテゴリから復習する"],
        href: "/", linkLabel: "ホームを見る" },
      { title: "練習履歴・絞り込み", when: "過去の回答・評価を振り返りたいとき。",
        does: "練習履歴と、確認できる評価の詳細を表示できます。",
        steps: ["右上のアカウントメニュー → 利用履歴", "「練習履歴」でモード・期間を選んで絞り込む", "対象の履歴を選択して詳細を見る"],
        note: "履歴は画面内のDialogで表示します。独立した履歴ページはありません。" },
      { title: "利用状況・アシスト履歴", when: "練習やアシストの利用状況を確認したいとき。",
        does: "回答数や利用枠、アシストの生成状態を確認できます。",
        steps: ["右上のアカウントメニュー → 利用履歴", "「利用状況」を開く。アシストの各生成状態は「練習履歴」で見る"],
        note: "アシストの生成候補本文は履歴から再表示できません。" },
    ],
  },
  {
    id: "account", title: "アカウント・FAQ", introduction: "ログインや困ったときの確認はこちら。",
    entries: [
      { title: "ログイン", when: "練習や履歴を利用するとき。",
        does: "メールアドレスと認証コードでログインします。",
        steps: ["ログイン画面でメールアドレスを入力", "届いた認証コードを入力して進む"],
        href: "/login/", linkLabel: "ログイン画面へ" },
      { title: "アカウント管理・ログアウト", when: "アカウント情報を確認したいとき・利用を終えるとき。",
        does: "右上のアカウントメニューから管理やログアウトを選べます。",
        steps: ["右上のアカウントメニューを開く", "「アカウント管理」または「ログアウト」を選ぶ"] },
    ],
  },
];
const faqs = [
  { q: "途中で画面を閉じたら、回答は消えますか？",
    a: "回答欄の下書きがこの端末に正常保存され、復元条件を満たしていれば戻せる場合があります。保存状態を確認してください。すべてのケースでの復元は保証されません。" },
  { q: "AIアシストは何回まで使用できますか？",
    a: "利用できる回数には枠があります。残りの利用枠は、右上のアカウントメニュー → 利用履歴 → 利用状況で確認してください。" },
  { q: "AI回答チェックとAI面接コーチの違いは何ですか？",
    a: "AI回答チェックは100点満点で回答を評価します。AI面接コーチは30点満点の評価と、最大3回の深掘り質問を通じて面接練習ができます。" },
  { q: "15問をすべて完了したらどうなりますか？",
    a: "「3分から始める」では達成画面が表示され、カテゴリを選んで復習できます。進捗カードでも全問達成を確認できます。" },
  { q: "過去の回答や評価はどこで確認できますか？",
    a: "右上のアカウントメニュー → 利用履歴 → 練習履歴を開きます。評価が完了している履歴では評価を確認できます。アシストの生成候補本文は履歴から再表示できません。" },
] as const;
const modes = [
  { value: "star", label: "経験・自己PR", answer: "エピソード作成アシスト（3案）" },
  { value: "prep", label: "強み・弱み・考え方", answer: "簡潔回答アシスト" },
  { value: "motivation", label: "志望理由", answer: "志望動機アシスト" },
  { value: "career_change", label: "転職のきっかけ", answer: "転職理由アシスト" },
  { value: "career_plan", label: "将来の目標", answer: "キャリアプランアシスト" },
  { value: "follow_up", label: "追加質問への回答", answer: "深掘り回答アシスト（追加質問の画面で使用）" },
] as const;

const Section = styled(Accordion)(({ theme }) => ({
  backgroundColor: theme.palette.background.paper, minWidth: 0,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.18),
  borderRadius: `${theme.shape.borderRadius}px !important`,
  boxShadow: theme.shadows[1], overflow: "hidden",
  "&:before": { display: "none" },
  "&.Mui-expanded": { margin: 0 },
}));
const Summary = styled(AccordionSummary)(({ theme }) => ({
  minHeight: 74, padding: theme.spacing(1.5, 2.5),
  "& .MuiAccordionSummary-content": { minWidth: 0 },
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.main, outlineOffset: -3 },
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1, 2) },
}));
const Content = styled(AccordionDetails)(({ theme }) => ({
  padding: theme.spacing(0, 2.5, 3), display: "grid", gap: theme.spacing(1.5),
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(0, 2, 2.5) },
}));
const EntryCard = styled("article")(({ theme }) => ({
  padding: theme.spacing(2), minWidth: 0, display: "grid", gap: theme.spacing(1),
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.12),
  backgroundColor: alpha(theme.palette.primary.light, 0.05),
}));
const ItemTitle = styled("h3")(({ theme }) => ({
  ...theme.typography.h3, margin: 0, fontWeight: 800,
}));
const SectionTitle = styled("span")(({ theme }) => ({
  ...theme.typography.h3, fontWeight: 800,
}));
const Label = styled("strong")(({ theme }) => ({
  color: theme.palette.primary.dark, fontWeight: 700,
}));
const P = styled("p")(({ theme }) => ({
  ...theme.typography.body2, margin: 0, lineHeight: 1.75,
  overflowWrap: "anywhere",
}));
const How = styled("ol")(({ theme }) => ({
  margin: 0, paddingLeft: theme.spacing(3),
  ...theme.typography.body2, lineHeight: 1.8,
}));
const SectionHeading = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.35), minWidth: 0,
}));
const Sections = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1.5),
  "& > *": { scrollMarginTop: theme.spacing(2.5) },
}));
const Purpose = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2),
  padding: theme.spacing(2),
  borderRadius: theme.shape.borderRadius,
  backgroundColor: alpha(theme.palette.primary.main, 0.055),
}));
const Answer = styled("p")(({ theme }) => ({
  ...theme.typography.body1, margin: 0,
  padding: theme.spacing(1.5), borderLeft: "4px solid " + theme.palette.primary.main,
  backgroundColor: theme.palette.background.paper, fontWeight: 700,
}));
function FeatureEntry({ entry }: { entry: Entry }) {
  return (
    <EntryCard>
      <ItemTitle>{entry.title}</ItemTitle>
      <P><Label>どんなときに使う？</Label> {entry.when}</P>
      <P><Label>何ができる？</Label> {entry.does}</P>
      <div><P><Label>どう使う？</Label></P><How>{entry.steps.map((s) => <li key={s}>{s}</li>)}</How></div>
      {entry.note && <P><Label>注意点：</Label> {entry.note}</P>}
      {entry.href && <Link href={entry.href}>{entry.linkLabel ?? "画面を開く"}</Link>}
    </EntryCard>
  );
}
function AssistPicker() {
  const [choice, setChoice] = useState<(typeof modes)[number]["value"]>("star");
  const selected = modes.find((mode) => mode.value === choice) ?? modes[0];
  return (
    <Purpose aria-label="回答アシストのおすすめ">
      <GuideSubheading>どんな回答を作りたい？</GuideSubheading>
      <FormControl fullWidth size="small">
        <InputLabel id="guide-assist-select-label">作りたい回答</InputLabel>
        <Select labelId="guide-assist-select-label" value={choice} label="作りたい回答"
          onChange={(event) => setChoice(event.target.value as typeof choice)}>
          {modes.map((mode) => <MenuItem key={mode.value} value={mode.value}>{mode.label}</MenuItem>)}
        </Select>
      </FormControl>
      <Answer role="status">おすすめ：{selected.answer}</Answer>
      <P>内容を入力 → AIが回答を生成 → 回答案を確認・編集 → 「この回答を使う」で反映します。コピーもできます。入力項目はモードによって異なります。必ず本人の経験・事実に合わせて確認してください。</P>
    </Purpose>
  );
}
function FAQ() {
  return (
    <div aria-label="よくある質問">
      <GuideSubheading>よくある質問</GuideSubheading>
      {faqs.map((faq) => (
        <Accordion key={faq.q} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreRoundedIcon aria-hidden="true" />}>{faq.q}</AccordionSummary>
          <AccordionDetails><P>{faq.a}</P></AccordionDetails>
        </Accordion>
      ))}
    </div>
  );
}
export function GuideFeatures() {
  const [expanded, setExpanded] = useState<string | null>(null);
  useEffect(() => {
    const showAnchor = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!categories.some((cat) => cat.id === id)) return;
      setExpanded(id);
      requestAnimationFrame(() => {
        const target = document.getElementById(id);
        if (typeof target?.scrollIntoView === "function") target.scrollIntoView({ block: "start" });
      });
    };
    showAnchor();
    window.addEventListener("hashchange", showAnchor);
    return () => window.removeEventListener("hashchange", showAnchor);
  }, []);
  return (
    <GuidePage>
      <GuideBack href="/guide/">← ガイドトップへ戻る</GuideBack>
      <GuideHeading>機能別ガイド</GuideHeading>
      <GuideLead>気になるカテゴリだけ開いて確認できます。説明にある操作は、現在のアプリの表示内容に合わせています。</GuideLead>
      <GuideSurface>
        <GuideEyebrow>全7カテゴリ</GuideEyebrow>
        <GuideSubheading>知りたい機能から探す</GuideSubheading>
        <Sections>
          {categories.map((cat, i) => (
            <Section key={cat.id} id={cat.id} expanded={expanded === cat.id}
              onChange={(_, open) => setExpanded(open ? cat.id : null)} disableGutters>
              <Summary expandIcon={<ExpandMoreRoundedIcon aria-hidden="true" />}
                aria-controls={cat.id + "-content"} id={cat.id + "-heading"}>
                <SectionHeading>
                  <GuideEyebrow>0{i + 1} / 07</GuideEyebrow>
                  <SectionTitle>{cat.title}</SectionTitle>
                  <P>{cat.introduction}</P>
                </SectionHeading>
              </Summary>
              <Content>
                {cat.id === "assist" && <AssistPicker />}
                {cat.entries.map((entry) => <FeatureEntry key={entry.title} entry={entry} />)}
                {cat.id === "account" && <FAQ />}
              </Content>
            </Section>
          ))}
        </Sections>
      </GuideSurface>
      <Link href="/guide/basic/">基本ガイドを見る</Link>
      <Link href="/">ホームへ戻る</Link>
    </GuidePage>
  );
}
