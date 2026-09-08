/**
 * @file withMobileDialogWidth.tsx
 * @description Dialog の Paper を iPhone SE 相当幅（375 - 余白16×2 = 343px）に固定するデコレータ。
 *   MUI Dialog は portal 描画かつ Paper 幅が window 基準のため、Storybook の viewport だけでは
 *   モバイル幅を再現できない。本デコレータで Paper を 343px に固定し、横溢れ検査を有効化する。
 */
import type { Decorator } from "@storybook/react-vite";

/** Paper を iPhone SE 相当幅に固定するデコレータ */
export const withMobileDialogWidth: Decorator = (Story) => (
  <>
    <style>
      {`.MuiDialog-paper{max-width:343px !important;width:343px !important;margin:16px !important;}`}
    </style>
    <Story />
  </>
);
