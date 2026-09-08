/**
 * @file theme.ts
 * @description 全コンポーネントで使う共通テーマを定義する
 */
import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    primary: {
      main: "#5f7d5a", // セージグリーン（落ち着いたアースカラー）
      light: "#8aa784",
      dark: "#415739",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#c2a878", // サンドベージュ（温かいアクセント）
      light: "#e0cba8",
      dark: "#a3895c",
      contrastText: "#3d3322", // ベージュ上は濃色文字で可読性確保
    },
    success: {
      main: "#2e7d32",
      light: "#4caf50",
      dark: "#1b5e20",
      contrastText: "#ffffff",
    },
    error: {
      main: "#d32f2f",
      light: "#ef5350",
      dark: "#c62828",
      contrastText: "#ffffff",
    },
    info: {
      main: "#0288d1",
      light: "#29b6f6",
      dark: "#01579b",
      contrastText: "#ffffff",
    },
    warning: {
      main: "#ed6c02",
      light: "#ff9800",
      dark: "#e65100",
      contrastText: "#ffffff",
    },
    background: {
      default: "#f5f2ea", // ウォームなサンドクリーム
      paper: "#ffffff", // glass は白の半透明を重ねるため据え置き
    },
    text: {
      primary: "#2f2a24", // ウォームチャコール
      secondary: "#6f6555", // ウォームトープ
    },
    grey: {
      50: "#f9f9f9",
      100: "#f5f5f5",
      200: "#eeeeee",
      300: "#e0e0e0",
      400: "#bdbdbd",
      500: "#9e9e9e",
      600: "#475569",
      700: "#334155",
      800: "#1e293b",
      900: "#0f172a",
    },
  },
  shape: {
    borderRadius: 16, // Increased for softer, more modern edges
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica Neue", Arial, sans-serif',
    h1: {
      fontWeight: 700,
      fontSize: "27px",
      lineHeight: 1.35,
      "@media (max-width:900px)": {
        fontSize: "22px",
      },
    },
    h2: {
      fontWeight: 600,
      fontSize: "21px",
      lineHeight: 1.4,
      "@media (max-width:900px)": {
        fontSize: "18px",
      },
    },
    h3: {
      fontWeight: 600,
      fontSize: "18px",
      lineHeight: 1.45,
      "@media (max-width:900px)": {
        fontSize: "16px",
      },
    },
    h4: {
      fontWeight: 600,
      fontSize: "33px",
      lineHeight: 1.235,
      "@media (max-width:900px)": {
        fontSize: "26px",
      },
    },
    h5: {
      fontWeight: 600,
      fontSize: "24px",
      lineHeight: 1.334,
      "@media (max-width:900px)": {
        fontSize: "20px",
      },
    },
    body1: {
      fontSize: "16px",
      lineHeight: 1.6,
      "@media (max-width:900px)": {
        fontSize: "14px",
      },
    },
    button: {
      textTransform: "none",
      fontWeight: 600,
      letterSpacing: "0.02em",
    },
  },
  components: {
    // 横スクロール症状の最後の砦＋画像はみ出し防止（原因は個別 styled() で解消する）
    MuiCssBaseline: {
      styleOverrides: {
        "html, body": { overflowX: "hidden" },
        img: { maxWidth: "100%", height: "auto" },
      },
    },
    // テーブルセルの余白・文字を xs で詰め、横スクロール量を減らす
    MuiTableCell: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down("sm")]: {
            padding: theme.spacing(1),
            fontSize: "0.8125rem",
          },
        }),
      },
    },
  },
  shadows: [
    "none",
    "0px 2px 4px rgba(0,0,0,0.1)",
    "0px 4px 8px rgba(0,0,0,0.12)",
    "0px 6px 12px rgba(0,0,0,0.15)",
    "0px 8px 16px rgba(0,0,0,0.18)",
    "0px 10px 20px rgba(0,0,0,0.2)",
    "0px 12px 24px rgba(0,0,0,0.22)",
    "0px 14px 28px rgba(0,0,0,0.24)",
    "0px 16px 32px rgba(0,0,0,0.26)",
    "0px 18px 36px rgba(0,0,0,0.28)",
    "0px 20px 40px rgba(0,0,0,0.3)",
    "0px 22px 44px rgba(0,0,0,0.32)",
    "0px 24px 48px rgba(0,0,0,0.34)",
    "0px 26px 52px rgba(0,0,0,0.36)",
    "0px 28px 56px rgba(0,0,0,0.38)",
    "0px 30px 60px rgba(0,0,0,0.4)",
    "0px 32px 64px rgba(0,0,0,0.42)",
    "0px 34px 68px rgba(0,0,0,0.44)",
    "0px 36px 72px rgba(0,0,0,0.46)",
    "0px 38px 76px rgba(0,0,0,0.48)",
    "0px 40px 80px rgba(0,0,0,0.5)",
    "0px 42px 84px rgba(0,0,0,0.52)",
    "0px 44px 88px rgba(0,0,0,0.54)",
    "0px 46px 92px rgba(0,0,0,0.56)",
    "0px 48px 96px rgba(0,0,0,0.58)",
  ],
});
