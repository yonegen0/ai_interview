/**
 * @file page.tsx
 * @description AI面接練習を始めるための仮トップページ
 */
"use client";

import AccessTimeRoundedIcon from "@mui/icons-material/AccessTimeRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded";
import BoltRoundedIcon from "@mui/icons-material/BoltRounded";
import BusinessCenterRoundedIcon from "@mui/icons-material/BusinessCenterRounded";
import EmojiEventsRoundedIcon from "@mui/icons-material/EmojiEventsRounded";
import FavoriteBorderRoundedIcon from "@mui/icons-material/FavoriteBorderRounded";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import HomeRoundedIcon from "@mui/icons-material/HomeRounded";
import LightbulbRoundedIcon from "@mui/icons-material/LightbulbRounded";
import PersonRoundedIcon from "@mui/icons-material/PersonRounded";
import RecordVoiceOverRoundedIcon from "@mui/icons-material/RecordVoiceOverRounded";
import TrendingUpRoundedIcon from "@mui/icons-material/TrendingUpRounded";
import type { SvgIconComponent } from "@mui/icons-material";
import { alpha, styled } from "@mui/material/styles";
import { useState } from "react";
import { Button } from "@/components/atoms/Button";

/** 面接カテゴリ */
type PracticeCategory = {
  title: string;
  description: string;
  icon: SvgIconComponent;
};

const categories: ReadonlyArray<PracticeCategory> = [
  {
    title: "転職理由",
    description: "前向きで納得感のある伝え方を練習",
    icon: TrendingUpRoundedIcon,
  },
  {
    title: "志望動機",
    description: "企業との接点を整理して言葉にする",
    icon: BusinessCenterRoundedIcon,
  },
  {
    title: "自己PR・強み",
    description: "あなたらしさが伝わるエピソードへ",
    icon: EmojiEventsRoundedIcon,
  },
  {
    title: "仕事経験",
    description: "経験と成果を分かりやすく説明する",
    icon: RecordVoiceOverRoundedIcon,
  },
];

const StyledPage = styled("div")(({ theme }) => ({
  minHeight: "100svh",
  paddingBottom: "88px",
  background: `
    radial-gradient(circle at 8% 4%, ${alpha(theme.palette.secondary.light, 0.42)} 0, transparent 32%),
    radial-gradient(circle at 94% 18%, ${alpha(theme.palette.primary.light, 0.24)} 0, transparent 30%),
    ${theme.palette.background.default}
  `,
}));

const StyledTopBar = styled("header")(({ theme }) => ({
  height: "68px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: theme.spacing(0, 3),
  borderBottom: `1px solid ${alpha(theme.palette.primary.main, 0.12)}`,
  backgroundColor: alpha(theme.palette.background.default, 0.78),
  backdropFilter: "blur(14px)",
  position: "sticky",
  top: 0,
  zIndex: 10,
  [theme.breakpoints.down("sm")]: {
    height: "60px",
    padding: theme.spacing(0, 2),
  },
}));

const StyledBrand = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  fontSize: "17px",
  fontWeight: 800,
  letterSpacing: "-0.02em",
  color: theme.palette.text.primary,
}));

const StyledLogo = styled("span")(({ theme }) => ({
  width: 34,
  height: 34,
  display: "grid",
  placeItems: "center",
  borderRadius: 11,
  color: theme.palette.common.white,
  background: `linear-gradient(145deg, ${theme.palette.primary.light}, ${theme.palette.primary.dark})`,
  boxShadow: `0 5px 16px ${alpha(theme.palette.primary.dark, 0.26)}`,
}));

const StyledUser = styled("button")(({ theme }) => ({
  border: 0,
  width: 38,
  height: 38,
  borderRadius: "50%",
  display: "grid",
  placeItems: "center",
  cursor: "pointer",
  color: theme.palette.primary.dark,
  backgroundColor: alpha(theme.palette.common.white, 0.72),
  boxShadow: `inset 0 0 0 1px ${alpha(theme.palette.primary.main, 0.18)}`,
}));

const StyledMain = styled("main")(({ theme }) => ({
  width: "min(100% - 32px, 920px)",
  margin: "0 auto",
  padding: theme.spacing(5, 0),
  [theme.breakpoints.down("sm")]: {
    width: "min(100% - 28px, 920px)",
    padding: theme.spacing(3, 0),
  },
}));

const StyledHero = styled("section")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "1fr auto",
  alignItems: "end",
  gap: theme.spacing(3),
  marginBottom: theme.spacing(4),
  [theme.breakpoints.down("sm")]: {
    gridTemplateColumns: "1fr",
    alignItems: "start",
    marginBottom: theme.spacing(3),
  },
}));

const StyledEyebrow = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.75),
  marginBottom: theme.spacing(1),
  color: theme.palette.primary.dark,
  fontSize: "12px",
  fontWeight: 800,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
}));

const StyledSparkleIcon = styled(AutoAwesomeRoundedIcon)({
  fontSize: 16,
});

const StyledTitle = styled("h1")(({ theme }) => ({
  margin: 0,
  maxWidth: 620,
  fontSize: "clamp(28px, 5vw, 44px)",
  lineHeight: 1.25,
  letterSpacing: "-0.035em",
  color: theme.palette.text.primary,
}));

const StyledLead = styled("p")(({ theme }) => ({
  maxWidth: 590,
  margin: theme.spacing(1.5, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
}));

const StyledTimeBadge = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.75),
  padding: theme.spacing(1, 1.5),
  borderRadius: 99,
  whiteSpace: "nowrap",
  color: theme.palette.primary.dark,
  fontSize: "13px",
  fontWeight: 700,
  backgroundColor: alpha(theme.palette.common.white, 0.72),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`,
  [theme.breakpoints.down("sm")]: {
    justifySelf: "start",
  },
}));

const StyledPanel = styled("section")(({ theme }) => ({
  padding: theme.spacing(3),
  borderRadius: 24,
  backgroundColor: alpha(theme.palette.common.white, 0.7),
  border: `1px solid ${alpha(theme.palette.common.white, 0.86)}`,
  boxShadow: `0 16px 50px ${alpha(theme.palette.primary.dark, 0.1)}`,
  backdropFilter: "blur(14px)",
  [theme.breakpoints.down("sm")]: {
    padding: theme.spacing(2),
    borderRadius: 20,
  },
}));

const StyledPanelHeading = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(2),
  marginBottom: theme.spacing(2),
}));

const StyledPanelTitle = styled("h2")(({ theme }) => ({
  margin: 0,
  fontSize: "20px",
  color: theme.palette.text.primary,
}));

const StyledStep = styled("span")(({ theme }) => ({
  color: theme.palette.text.secondary,
  fontSize: "12px",
  fontWeight: 700,
}));

const StyledCategoryGrid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.spacing(1.5),
  [theme.breakpoints.down("sm")]: {
    gridTemplateColumns: "1fr",
    gap: theme.spacing(1),
  },
}));

const StyledCategory = styled("button", {
  shouldForwardProp: (prop) => prop !== "$selected",
})<{ $selected: boolean }>(({ theme, $selected }) => ({
  width: "100%",
  border: `1px solid ${alpha(theme.palette.primary.main, 0.13)}`,
  borderRadius: 17,
  padding: theme.spacing(2),
  display: "grid",
  gridTemplateColumns: "46px 1fr auto",
  alignItems: "center",
  gap: theme.spacing(1.5),
  textAlign: "left",
  cursor: "pointer",
  color: theme.palette.text.primary,
  backgroundColor: $selected
    ? alpha(theme.palette.primary.light, 0.18)
    : alpha(theme.palette.background.paper, 0.62),
  boxShadow: $selected
    ? `inset 0 0 0 1px ${alpha(theme.palette.primary.main, 0.45)}`
    : "none",
  transition: theme.transitions.create(["transform", "border-color", "box-shadow", "background-color"]),
  "&:hover, &:focus-visible": {
    transform: "translateY(-2px)",
    borderColor: alpha(theme.palette.primary.main, 0.45),
    backgroundColor: theme.palette.background.paper,
    boxShadow: `0 10px 28px ${alpha(theme.palette.primary.dark, 0.12)}`,
    outline: "none",
  },
}));

const StyledCategoryIcon = styled("span")(({ theme }) => ({
  width: 46,
  height: 46,
  display: "grid",
  placeItems: "center",
  borderRadius: 14,
  color: theme.palette.primary.dark,
  backgroundColor: alpha(theme.palette.primary.light, 0.2),
}));

const StyledCategoryTitle = styled("strong")({
  display: "block",
  fontSize: "15px",
  marginBottom: 3,
});

const StyledCategoryDescription = styled("span")(({ theme }) => ({
  display: "block",
  color: theme.palette.text.secondary,
  fontSize: "12px",
  lineHeight: 1.5,
}));

const StyledFooterRow = styled("div")(({ theme }) => ({
  marginTop: theme.spacing(2.5),
  paddingTop: theme.spacing(2),
  borderTop: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: {
    alignItems: "stretch",
    flexDirection: "column",
  },
}));

const StyledHint = styled("p")(({ theme }) => ({
  margin: 0,
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.75),
  color: theme.palette.text.secondary,
  fontSize: "12px",
}));

const StyledStartButton = styled(Button)(({ theme }) => ({
  minHeight: 46,
  color: theme.palette.common.white,
  borderColor: theme.palette.primary.main,
  background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
  boxShadow: `0 8px 24px ${alpha(theme.palette.primary.dark, 0.24)}`,
  "&:hover": {
    color: theme.palette.common.white,
    background: `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.main})`,
  },
}));

const StyledBottomNav = styled("nav")(({ theme }) => ({
  position: "fixed",
  zIndex: 20,
  left: "50%",
  bottom: 12,
  transform: "translateX(-50%)",
  width: "min(calc(100% - 24px), 460px)",
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  padding: theme.spacing(0.75),
  borderRadius: 20,
  backgroundColor: alpha(theme.palette.common.white, 0.88),
  border: `1px solid ${alpha(theme.palette.common.white, 0.92)}`,
  boxShadow: `0 12px 36px ${alpha(theme.palette.primary.dark, 0.18)}`,
  backdropFilter: "blur(16px)",
}));

const StyledNavItem = styled("button", {
  shouldForwardProp: (prop) => prop !== "$active",
})<{ $active?: boolean }>(({ theme, $active }) => ({
  border: 0,
  borderRadius: 14,
  padding: theme.spacing(0.75),
  display: "grid",
  justifyItems: "center",
  gap: 2,
  cursor: "pointer",
  fontSize: "11px",
  fontWeight: 700,
  color: $active ? theme.palette.primary.dark : theme.palette.text.secondary,
  backgroundColor: $active ? alpha(theme.palette.primary.light, 0.2) : "transparent",
}));

/**
 * 練習カテゴリを選択できる仮トップページを表示する
 * @returns トップページUI
 */
export default function HomePage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  return (
    <StyledPage>
      <StyledTopBar>
        <StyledBrand>
          <StyledLogo aria-hidden="true">
            <BoltRoundedIcon fontSize="small" />
          </StyledLogo>
          Interview Pocket
        </StyledBrand>
        <StyledUser type="button" aria-label="プロフィールを開く">
          <PersonRoundedIcon fontSize="small" />
        </StyledUser>
      </StyledTopBar>

      <StyledMain>
        <StyledHero>
          <div>
            <StyledEyebrow>
              <StyledSparkleIcon />
              Quick practice
            </StyledEyebrow>
            <StyledTitle>今日の3分が、面接の自信になる。</StyledTitle>
            <StyledLead>
              カテゴリを選んで一問だけ。あなたの回答をAIが短く、分かりやすくフィードバックします。
            </StyledLead>
          </div>
          <StyledTimeBadge>
            <AccessTimeRoundedIcon fontSize="small" />
            約3分で完了
          </StyledTimeBadge>
        </StyledHero>

        <StyledPanel aria-labelledby="category-title">
          <StyledPanelHeading>
            <StyledPanelTitle id="category-title">何を練習しますか？</StyledPanelTitle>
            <StyledStep>STEP 1 / 2</StyledStep>
          </StyledPanelHeading>

          <StyledCategoryGrid>
            {categories.map((category) => {
              const CategoryIcon = category.icon;
              return (
                <StyledCategory
                  type="button"
                  key={category.title}
                  $selected={selectedCategory === category.title}
                  aria-pressed={selectedCategory === category.title}
                  onClick={() => setSelectedCategory(category.title)}
                >
                  <StyledCategoryIcon aria-hidden="true">
                    <CategoryIcon />
                  </StyledCategoryIcon>
                  <span>
                    <StyledCategoryTitle>{category.title}</StyledCategoryTitle>
                    <StyledCategoryDescription>{category.description}</StyledCategoryDescription>
                  </span>
                  <ArrowForwardRoundedIcon color="primary" fontSize="small" />
                </StyledCategory>
              );
            })}
          </StyledCategoryGrid>

          <StyledFooterRow>
            <StyledHint>
              <LightbulbRoundedIcon fontSize="small" />
              回答は100〜300文字がおすすめです
            </StyledHint>
            <StyledStartButton
              endIcon={<ArrowForwardRoundedIcon />}
              disabled={!selectedCategory}
            >
              {selectedCategory ? `${selectedCategory}を始める` : "カテゴリを選択"}
            </StyledStartButton>
          </StyledFooterRow>
        </StyledPanel>
      </StyledMain>

      <StyledBottomNav aria-label="メインナビゲーション">
        <StyledNavItem type="button" $active aria-current="page">
          <HomeRoundedIcon fontSize="small" />
          練習
        </StyledNavItem>
        <StyledNavItem type="button">
          <HistoryRoundedIcon fontSize="small" />
          履歴
        </StyledNavItem>
        <StyledNavItem type="button">
          <FavoriteBorderRoundedIcon fontSize="small" />
          お気に入り
        </StyledNavItem>
      </StyledBottomNav>
    </StyledPage>
  );
}
