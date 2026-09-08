import type { StorybookConfig } from "@storybook/react-vite";
import type { Plugin } from "vite";
import { mergeConfig } from "vite";
import path from "path";
import { fileURLToPath } from "url";

// ESM環境で __dirname を再現する
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const nextNavigationStubPath = path.resolve(__dirname, "mocks", "next-navigation.stub.ts");
const nextLinkStubPath = path.resolve(__dirname, "mocks", "next-link.stub.tsx");

/**
 * 絶対パス解決後でも各 hook をスタブへ寄せる（alias だけだと本物が残ることがある）
 */
const createStorybookHookStubResolvePlugin = (): Plugin => ({
  name: "storybook-hook-stub-resolve",
  enforce: "pre",
  resolveId(source, importer) {
    if (source === "next/navigation") {
      return nextNavigationStubPath;
    }
    if (source === "next/link") {
      return nextLinkStubPath;
    }
    return undefined;
  },
});

const config: StorybookConfig = {
  stories: ["../stories/**/*.mdx", "../stories/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: [
    "@chromatic-com/storybook",
  ],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  async viteFinal(config) {
    return mergeConfig(config, {
      plugins: [createStorybookHookStubResolvePlugin()],
      resolve: {
        alias: {
          "@": path.resolve(__dirname, "..", "src"),
          "next/navigation": nextNavigationStubPath,
          "next/link": nextLinkStubPath,
        },
      },
    });
  },
};

export default config;
