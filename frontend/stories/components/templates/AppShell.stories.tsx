/**
 * @file AppShell.stories.tsx
 * @description AppShell コンポーネントの表示確認用ストーリー。ロール別ナビ表示とパス別分岐を検証する。
 */
import type { Meta, StoryObj } from "@storybook/react-vite";
import { AppShell } from "@/components/templates/AppShell";
import { __setMockAuthClaims } from "../../../.storybook/mocks/auth-guard.stub";
import { __setMockPathname } from "../../../.storybook/mocks/next-navigation.stub";
import { assertNoHorizontalOverflow } from "../../test-utils/assertNoHorizontalOverflow";

const meta: Meta<typeof AppShell> = {
  title: "Components/Templates/AppShell",
  component: AppShell,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    children: (
      <div>
        <h2>メインエリアのサンプル</h2>
        <p>ここに各画面の本文が表示されます。</p>
      </div>
    ),
  },
};

export default meta;
type Story = StoryObj<typeof AppShell>;

/**
 * OwnerNav: role="owner"
 * 経営者ロールで表示される 4 項目（ダッシュボード／取込／レポート／比較）を確認する。
 */
export const OwnerNav: Story = {
  beforeEach: () => {
    __setMockPathname("/dashboard");
    __setMockAuthClaims({
      role: "owner",
      email: "owner@example.com",
      storeId: "store-001",
    });
  },
};

/**
 * StaffNav: role="staff"
 * 従業員ロールで設定・処理ログが非表示になることを確認する。
 */
export const StaffNav: Story = {
  beforeEach: () => {
    __setMockPathname("/reports");
    __setMockAuthClaims({
      role: "staff",
      email: "staff@example.com",
      storeId: "store-001",
    });
  },
};

/**
 * AdminNav: role="admin"
 * 管理者ロールで全 6 項目（店舗設定・処理ログを含む）が表示されることを確認する。
 */
export const AdminNav: Story = {
  beforeEach: () => {
    __setMockPathname("/settings");
    __setMockAuthClaims({
      role: "admin",
      email: "admin@example.com",
      storeId: "store-001",
    });
  },
};

/**
 * LoginRoute: pathname="/login"
 * ログイン画面ではナビ・ヘッダーをバイパスし children のみ表示することを確認する。
 */
export const LoginRoute: Story = {
  beforeEach: () => {
    __setMockPathname("/login");
    __setMockAuthClaims({
      role: "owner",
      email: "owner@example.com",
      storeId: "store-001",
    });
  },
};

/**
 * Mobile: 375px 幅で永続 Drawer が一時 Drawer（オーバーレイ）へ切り替わり、
 * 本体が押し潰されず横スクロールが発生しないことを検証する。
 */
export const Mobile: Story = {
  ...OwnerNav,
  parameters: {
    ...OwnerNav.parameters,
    viewport: { defaultViewport: "iphoneSe" },
  },
  play: assertNoHorizontalOverflow,
};
