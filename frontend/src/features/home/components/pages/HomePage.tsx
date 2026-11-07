/** @file HomePage.tsx @description 練習導線を案内するホーム画面の構成。 */
"use client";

import { styled } from "@mui/material/styles";
import { HomeHero } from "../organisms/HomeHero";
import { HomeNavigation } from "../organisms/HomeNavigation";
import { HomeProgress } from "../organisms/HomeProgress";

const PageContent = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2.5),
  minWidth: 0,
  [theme.breakpoints.up("md")]: { gap: theme.spacing(3.5) },
}));

/** モバイル優先のホーム画面。 */
export const HomePage = () => (
  <PageContent>
    <HomeHero />
    <HomeProgress />
    <HomeNavigation />
  </PageContent>
);
